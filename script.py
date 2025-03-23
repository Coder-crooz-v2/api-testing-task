import requests
import time
import string
import json
import os
import threading
import random
from collections import deque

def discover_valid_endpoints(base_url="http://35.200.185.69:8000"):

    """
    The function tests combinations of different version prefixes (v1, v2, etc.)
    with different endpoint names (autocomplete, search, etc.) and identifies
    which combinations return a successful 200 status code when queried.

    Parameters:
        base_url (str): The base URL of the API server to test -> "http://35.200.185.69:8000"
    
    Returns:
        list: A list of dictionaries containing information about valid endpoints.
              Each dictionary contains:
              - url (str): The full URL of the endpoint
              - path (str): The path component (version/endpoint)
              - version (str): The API version prefix
              - endpoint (str): The endpoint name
    """
    print("\n=== STEP 1: DISCOVERING VALID API ENDPOINTS ===")
    
    versions = ["v1", "v2", "v3", "v4", "v5", "api", "beta"]
    endpoints = ["autocomplete", "complete", "suggest", "search", "query", "names", "lookup", "find", "dictionary"]
    
    valid_endpoints = []
    
    for version in versions:
        for endpoint in endpoints:
            url = f"{base_url}/{version}/{endpoint}"
            try:
                response = requests.get(f"{url}?query=a", timeout=3)
                if response.status_code == 200:
                    valid_endpoints.append({
                        "url": url,
                        "path": f"{version}/{endpoint}",
                        "version": version,
                        "endpoint": endpoint
                    })
                    print(f"Found valid endpoint: GET {url}")
                else:
                    print(f"Endpoint returned status {response.status_code}: GET {url}")
            except Exception as e:
                print(f"Error checking endpoint: GET {url} - {str(e)}")
    
    print(f"\nFound {len(valid_endpoints)} valid endpoints")
    for i, ep in enumerate(valid_endpoints, 1):
        print(f"{i}. {ep['path']} - {ep['url']}")
    
    return valid_endpoints

def test_rate_limits(endpoints, base_url="http://35.200.185.69:8000"):

    """
    The function sends requests in progressively larger batches to each endpoint until
    rate limiting is detected (429 status code). It then calculates a safe request rate
    based on the results, targeting approximately 80% of the estimated limit.
    
    Parameters:
        endpoints (list): List of endpoint dictionaries from discover_valid_endpoints
        base_url (str): The base URL of the API server: "http://35.200.185.69:8000"
    
    Returns:
        endpoints (list): The input endpoints list, enhanced with rate limit information. Each endpoint
                          dictionary is updated with:
                          - rate_limit (float): Estimated safe request rate per second
                          - rate_limit_results (dict): Detailed test results for different batch sizes
    """
    print("\n=== STEP 2: TESTING RATE LIMITS FOR EACH ENDPOINT ===")
    
    for endpoint in endpoints:
        url = endpoint["url"]
        path = endpoint["path"]
        
        print(f"\nTesting rate limits for: {path} ({url})")
        
        batch_sizes = [30, 60, 90, 120]
        rate_limit_found = False
        results = {}
        
        for batch_size in batch_sizes:
            if rate_limit_found:
                break
                
            print(f"Testing batch size of {batch_size} requests...")
            
            success_count = 0
            rate_limited_count = 0
            start_time = time.time()
            
            for i in range(batch_size):
                try:
                    random_str = ''.join(random.choices(string.ascii_lowercase, k=5))
                    response = requests.get(f"{url}?query={random_str}", timeout=3)
                    
                    if response.status_code == 200:
                        success_count += 1
                    elif response.status_code == 429:
                        rate_limited_count += 1
                        rate_limit_found = True
                    
                    time.sleep(0.1)
                    
                except Exception as e:
                    print(f"  Error during rate limit test: {str(e)}")
            
            end_time = time.time()
            duration = end_time - start_time
            
            results[batch_size] = {
                "success": success_count,
                "rate_limited": rate_limited_count,
                "duration": duration,
                "rate": success_count / duration if duration > 0 else 0
            }
            
            print(f"Results: {success_count} successful, {rate_limited_count} rate limited, took {duration:.2f} seconds")
            
            if rate_limit_found:
                print(f"Rate limit exceeded for {path} at batch size {batch_size}")
            else:
                print(f"Waiting 90 seconds before next batch test...")
                time.sleep(90)
        
        if rate_limit_found:
            limit_batch = max([b for b, r in results.items() if r["rate_limited"] > 0])
            rate_limit = results[limit_batch]["success"] / 60 * 0.8
        else:
            max_batch = max(results.keys())
            rate_limit = results[max_batch]["success"] / 60 * 0.8
        
        endpoint["rate_limit"] = rate_limit
        endpoint["rate_limit_results"] = results
    
    print("\nEndpoint rate limits:")
    for endpoint in endpoints:
        print(f"{endpoint['path']}: {endpoint['rate_limit']:.2f} req/sec")
    
    print("\nDetailed rate limit test results:\n")
    for endpoint in endpoints:
        path = endpoint["path"]
        results = endpoint["rate_limit_results"]
        
        print(f"{path}:")
        for batch_size, result in results.items():
            success_rate = result["success"] / batch_size * 100 if batch_size > 0 else 0
            print(f" Batch size {batch_size}:")
            print(f" - Success: {result['success']}/{batch_size} ({success_rate:.1f}%)")
            print(f" - Rate limited: {result['rate_limited']}")
            print(f" - Duration: {result['duration']:.2f} seconds")
            print(f" - Actual rate: {result['rate']:.2f} req/sec")
    
    return endpoints

class SmartRateLimiter:

    """
    The class manages request timing across multiple endpoints, tracking success and
    failure rates to dynamically adjust request pacing. It implements adaptive backoff
    when rate limits are encountered and provides statistical tracking of requests.
    
    Parameters:
        endpoints (list): List of endpoint dictionaries with rate limit information
    
    Attributes:
        endpoints (dict): Mapping of endpoint paths to their configuration data
        locks (dict): Thread synchronization locks for each endpoint
        request_times (dict): Timestamps of recent requests for each endpoint
        request_counts (dict): Total request counts by endpoint
        success_counts (dict): Successful request counts by endpoint
        failure_counts (dict): Failed request counts by endpoint
        rate_limit_counts (dict): Rate limit error counts by endpoint
        adaptive_backoff (dict): Current backoff delay for each endpoint
    
    """
    def __init__(self, endpoints):
        self.endpoints = {ep["path"]: ep for ep in endpoints}
        self.locks = {path: threading.Lock() for path in self.endpoints}
        self.request_times = {path: [] for path in self.endpoints}
        self.request_counts = {path: 0 for path in self.endpoints}
        self.success_counts = {path: 0 for path in self.endpoints}
        self.failure_counts = {path: 0 for path in self.endpoints}
        self.rate_limit_counts = {path: 0 for path in self.endpoints}
        self.adaptive_backoff = {path: 0 for path in self.endpoints}
        
    def wait_if_needed(self, path):

        """
        This method enforces rate limits by tracking request timestamps and
        calculating appropriate delays. It adds random jitter to prevent
        request synchronization issues.

        Parameters:
            path (str): The endpoint path to check rate limits for
            
        Returns:
            wait_time (float): The total wait time in seconds (including jitter)
        
        """
        if path not in self.endpoints:
            print(f"Unknown endpoint path: {path}")
            time.sleep(1)
            return 1.0
        
        endpoint = self.endpoints[path]
        rate_limit = endpoint["rate_limit"]
        
        period = 60
        max_requests = int(rate_limit * period)
        
        with self.locks[path]:
            current_time = time.time()
            
            self.request_times[path] = [t for t in self.request_times[path] 
                                       if current_time - t < period]
            
            recent_requests = len(self.request_times[path])
            
            wait_time = 0
            
            if recent_requests >= max_requests:
                oldest = min(self.request_times[path]) if self.request_times else current_time
                wait_time = period - (current_time - oldest) + 0.1 + self.adaptive_backoff[path]
                
                if wait_time > 0:
                    time.sleep(wait_time)
            
            self.request_times[path].append(time.time())
            self.request_counts[path] += 1
            
            jitter = random.uniform(0, 0.1)
            time.sleep(jitter)
            
            return wait_time + jitter
    
    def report_success(self, path):

        """
        On successful requests, this method decreases the adaptive backoff
        value to gradually increase throughput if previous backoffs occurred.

        Parameters:
            path (str): The endpoint path that had a successful request
        
        """
        if path not in self.endpoints:
            return
            
        with self.locks[path]:
            self.success_counts[path] += 1
            
            if self.adaptive_backoff[path] > 0:
                self.adaptive_backoff[path] = max(0, self.adaptive_backoff[path] - 0.01)
    
    def report_failure(self, path, rate_limited=False):

        """
        When rate limit errors occur repeatedly, this method increases the adaptive
        backoff for the endpoint to reduce request frequency.
        
        Parameters:
            path (str): The endpoint path that had a failed request
            rate_limited (bool): Whether the failure was due to rate limiting (429)
                                Default: False
        """
        if path not in self.endpoints:
            return
            
        with self.locks[path]:
            self.failure_counts[path] += 1
            
            if rate_limited:
                self.rate_limit_counts[path] += 1
                
                if self.rate_limit_counts[path] >= 3:
                    self.adaptive_backoff[path] += random.uniform(0.1, 0.5)
                    print(f"Increased backoff for {path} to {self.adaptive_backoff[path]:.2f}s")
                    self.rate_limit_counts[path] = 0
    
    def get_stats(self):

        """
        Return statistics about requests made.
        
        Parameters: None
            
        Returns:
            stats (dict): A dictionary mapping endpoint paths to statistics dictionaries with:
                        - requests (int): Total request count
                        - success (int): Successful request count
                        - failure (int): Failed request count
                        - rate_limits (int): Rate limit error count
                        - backoff (float): Current adaptive backoff value
        
        """
        stats = {}
        for path in self.endpoints:
            stats[path] = {
                "requests": self.request_counts[path],
                "success": self.success_counts[path],
                "failure": self.failure_counts[path],
                "rate_limits": self.rate_limit_counts[path],
                "backoff": self.adaptive_backoff[path]
            }
        return stats

class NameExtractor:
    
    """    
    This class manages the process of systematically querying endpoints to extract
    all available names. It implements breadth-first traversal of the query space,
    parallelization across endpoints, caching of intermediate results, and tracking
    of unique names by endpoint.
    
    Parameters:
        endpoints (list): List of endpoint dictionaries with configuration
        rate_limiter (SmartRateLimiter): Rate limiter instance to manage request timing
    
    Attributes:
        endpoints (list): List of endpoint configurations
        rate_limiter (SmartRateLimiter): Rate limiter for managing request timing
        all_names (set): Set of all unique names found across all endpoints
        names_by_endpoint (dict): Mapping of endpoint paths to sets of names
        processed_queries (dict): Mapping of endpoint paths to sets of processed queries
        lock (threading.Lock): Lock for thread-safe access to shared data
        cache_dir (str): Directory for caching intermediate results
    
    """
    def __init__(self, endpoints, rate_limiter):
        self.endpoints = endpoints
        self.rate_limiter = rate_limiter
        self.all_names = set()
        self.names_by_endpoint = {ep["path"]: set() for ep in endpoints}
        self.processed_queries = {ep["path"]: set() for ep in endpoints}
        self.lock = threading.Lock()
        self.cache_dir = "name_cache"
        
        if not os.path.exists(self.cache_dir):
            os.makedirs(self.cache_dir)
        
        self.load_cached_data()
    
    def load_cached_data(self):

        """
        Loads cached name sets and processed query sets from JSON files in the cache
        directory, enabling resumption of previous extraction runs.

        Parameters: None

        Returns: None

        """
        try:
            cache_file = os.path.join(self.cache_dir, "all_names.json")
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    self.all_names = set(json.load(f))
                print(f"Loaded {len(self.all_names)} names from cache")
            
            for endpoint in self.endpoints:
                path = endpoint["path"]
                ep_cache_file = os.path.join(self.cache_dir, f"{path.replace('/', '_')}_names.json")
                if os.path.exists(ep_cache_file):
                    with open(ep_cache_file, 'r') as f:
                        self.names_by_endpoint[path] = set(json.load(f))
                    print(f"Loaded {len(self.names_by_endpoint[path])} names for {path} from cache")
                
                queries_file = os.path.join(self.cache_dir, f"{path.replace('/', '_')}_queries.json")
                if os.path.exists(queries_file):
                    with open(queries_file, 'r') as f:
                        self.processed_queries[path] = set(json.load(f))
                    print(f"Loaded {len(self.processed_queries[path])} processed queries for {path}")
        except Exception as e:
            print(f"Error loading cache: {e}")
    
    def save_to_cache(self, path=None):
        """
        Saves the current state of name extraction to JSON files in the cache directory,
        including all names, names by endpoint, and processed queries.
        
        Parameters:
            path (str, optional): If provided, only save data for this endpoint path.
                                 If None, save all data. Default: None
            
        Returns: None

        """
        try:
            if path is None:
                cache_file = os.path.join(self.cache_dir, "all_names.json")
                with open(cache_file, 'w') as f:
                    json.dump(list(self.all_names), f)
                
                for ep_path, names in self.names_by_endpoint.items():
                    ep_cache_file = os.path.join(self.cache_dir, f"{ep_path.replace('/', '_')}_names.json")
                    with open(ep_cache_file, 'w') as f:
                        json.dump(list(names), f)
                    
                    queries_file = os.path.join(self.cache_dir, f"{ep_path.replace('/', '_')}_queries.json")
                    with open(queries_file, 'w') as f:
                        json.dump(list(self.processed_queries[ep_path]), f)
            else:
                ep_cache_file = os.path.join(self.cache_dir, f"{path.replace('/', '_')}_names.json")
                with open(ep_cache_file, 'w') as f:
                    json.dump(list(self.names_by_endpoint[path]), f)
                
                queries_file = os.path.join(self.cache_dir, f"{path.replace('/', '_')}_queries.json")
                with open(queries_file, 'w') as f:
                    json.dump(list(self.processed_queries[path]), f)
        except Exception as e:
            print(f"Error saving cache: {e}")
    
    def make_request(self, path, query):
        """
        Makes an HTTP request through the rate limiter and handles response codes and
        exceptions appropriately, reporting outcomes to the rate limiter.
        
        Parameters:
            path (str): The endpoint path to query
            query (str): The query string to send
            
        Returns:
            response or None: The JSON response if successful, None on failure

        """
        if path not in self.names_by_endpoint:
            print(f"Unknown endpoint path: {path}")
            return None
        
        endpoint = next((ep for ep in self.endpoints if ep["path"] == path), None)
        if not endpoint:
            print(f"Could not find endpoint info for {path}")
            return None
        
        self.rate_limiter.wait_if_needed(path)
        
        url = endpoint["url"]
        try:
            response = requests.get(f"{url}?query={query}", timeout=5)
            if response.status_code == 200:
                self.rate_limiter.report_success(path)
                return response.json()
            elif response.status_code == 429:
                self.rate_limiter.report_failure(path, rate_limited=True)
                print(f"Rate limited on {path} for query '{query}'")
                time.sleep(2)
                return None
            else:
                self.rate_limiter.report_failure(path)
                print(f"Error {response.status_code} for {path} with query '{query}'")
                return None
        except Exception as e:
            self.rate_limiter.report_failure(path)
            print(f"Exception for {path} with query '{query}': {str(e)}")
            time.sleep(1)
            return None
    
    def process_endpoint(self, endpoint):
        """
        Implements breadth-first traversal of the query space for a specific endpoint,
        extending the search when results suggest more names might be available.

         Parameters:
            endpoint (dict): The endpoint configuration dictionary
            
        Returns:
            names_by_endpoint (set): The set of names found for this endpoint
            requests (int): The total number of requests made during extraction

        """
        path = endpoint["path"]
        print(f"\nExtracting names from endpoint: {path}")
        
        queue = deque()
        processed = self.processed_queries[path]
        
        for char in string.ascii_lowercase:
            if char not in processed:
                queue.append(char)
                processed.add(char)
        
        start_time = time.time()
        requests_made = 0
        last_save_time = start_time
        
        while queue:
            current_query = queue.popleft()
            
            result = self.make_request(path, current_query)
            requests_made += 1
            
            if result and "results" in result:
                names = result.get("results", [])
                
                with self.lock:
                    before_count = len(self.names_by_endpoint[path])
                    self.names_by_endpoint[path].update(names)
                    self.all_names.update(names)
                    after_count = len(self.names_by_endpoint[path])
                    new_count = after_count - before_count
                
                if new_count > 0:
                    print(f" Query '{current_query}': Found {new_count} new names, total: {after_count}")
                
                if len(names) >= 9:
                    for char in string.ascii_lowercase:
                        next_query = current_query + char
                        if next_query not in processed:
                            queue.append(next_query)
                            processed.add(next_query)
            
            current_time = time.time()
            if current_time - last_save_time > 60:
                elapsed = current_time - start_time
                req_per_sec = requests_made / elapsed if elapsed > 0 else 0
                print(f" Progress: {len(self.names_by_endpoint[path])} names, {requests_made} requests, {req_per_sec:.2f} req/sec, {len(queue)} queries left")
                self.save_to_cache(path)
                last_save_time = current_time
        
        self.save_to_cache(path)
        
        elapsed_time = time.time() - start_time
        print(f"\nEndpoint {path} extraction complete:")
        print(f"  Found {len(self.names_by_endpoint[path])} names")
        print(f"  Made {requests_made} requests")
        print(f"  Time: {elapsed_time:.2f} seconds")
        print(f"  Rate: {requests_made/elapsed_time:.2f} req/sec")
        
        return self.names_by_endpoint[path], requests_made
    
    def extract_names_parallel(self):
        """
        Manages parallel extraction across all endpoints and consolidates results, saving
        the extracted names to files and calculating which names are unique to each endpoint.

        Parameters: None
            
        Returns:
            all_names (set): The set of all unique names found across all endpoints
            endpoint_stats (list): List of dictionaries containing statistics for each endpoint
            unique_by_endpoint (dict): Mapping of endpoint paths to sets of unique names

        """
        print("\n=== STEP 3: EXTRACTING NAMES FROM ALL ENDPOINTS ===")
        
        threads = []
        results = {}
        
        for endpoint in self.endpoints:
            thread = threading.Thread(
                target=self.worker_thread_for_endpoint,
                args=(endpoint, results),
                name=f"Extractor-{endpoint['path']}"
            )
            thread.daemon = True
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        unique_by_endpoint = self.calculate_unique_names()
        
        endpoint_stats = []
        for endpoint in self.endpoints:
            path = endpoint["path"]
            stats = {
                "endpoint": path,
                "total_names": len(self.names_by_endpoint[path]),
                "unique_names": len(unique_by_endpoint[path]),
                "requests": results.get(path, {}).get("requests", 0),
                "rate_limit": endpoint["rate_limit"]
            }
            endpoint_stats.append(stats)
        
        self.save_to_cache()
        
        with open("all_extracted_names.txt", "w") as f:
            for name in sorted(self.all_names):
                f.write(f"{name}\n")
        
        for endpoint in self.endpoints:
            path = endpoint["path"]
            unique_file = f"unique_names_{path.replace('/', '_')}.txt"
            with open(unique_file, "w") as f:
                for name in sorted(unique_by_endpoint[path]):
                    f.write(f"{name}\n")
        
        return self.all_names, endpoint_stats, unique_by_endpoint
    
    def worker_thread_for_endpoint(self, endpoint, results):
        """
        Thread implementation that processes a single endpoint and captures statistics
        in the shared results dictionary.

        Parameters:
            endpoint (dict): The endpoint configuration dictionary
            results (dict): Shared dictionary for storing results by endpoint path
            
        Returns: None
        
        """
        path = endpoint["path"]
        
        try:
            names, requests = self.process_endpoint(endpoint)
            results[path] = {
                "names": len(names),
                "requests": requests
            }
        except Exception as e:
            print(f"Error in worker thread for {path}: {e}")
            results[path] = {
                "names": 0,
                "requests": 0,
                "error": str(e)
            }
    
    def calculate_unique_names(self):
        """
        Determines which names appear exclusively in one endpoint by comparing the
        name sets across all endpoints.

        Parameters: None
            
        Returns:
            unique_by_endpoints (dict): Mapping of endpoint paths to sets of names that are unique to that endpoint

        """
        unique_by_endpoint = {path: set() for path in self.names_by_endpoint}
        
        for ep1_path, names_in_ep1 in self.names_by_endpoint.items():
            for name in names_in_ep1:
                found_elsewhere = False
                for ep2_path, names_in_ep2 in self.names_by_endpoint.items():
                    if ep1_path != ep2_path and name in names_in_ep2:
                        found_elsewhere = True
                        break
                if not found_elsewhere:
                    unique_by_endpoint[ep1_path].add(name)
        
        return unique_by_endpoint

def main():
    """
    This function orchestrates the entire workflow:
    1. Discovers valid API endpoints
    2. Tests rate limits for each endpoint
    3. Creates a rate limiter based on the discovered limits
    4. Extracts names from all endpoints in parallel
    5. Calculates statistics and unique names by endpoint
    6. Saves results to files and prints a summary
    
    The function implements a progressive approach where each step builds on the
    results of previous steps to efficiently extract all available names from the API.

    Parameters: None
        
    Returns: None
    
    """
    base_url = "http://35.200.185.69:8000"
    
    valid_endpoints = discover_valid_endpoints(base_url)
    
    if not valid_endpoints:
        print("No valid endpoints found. Exiting.")
        return
    
    endpoints_with_limits = test_rate_limits(valid_endpoints, base_url)
    
    rate_limiter = SmartRateLimiter(endpoints_with_limits)
    
    extractor = NameExtractor(endpoints_with_limits, rate_limiter)
    all_names, endpoint_stats, unique_by_endpoint = extractor.extract_names_parallel()
    
    print("\n=== EXTRACTION SUMMARY ===")
    print(f"Total unique names: {len(all_names)}")
    
    for stats in endpoint_stats:
        print(f"{stats['endpoint']}: {stats['total_names']} names, {stats['unique_names']} unique, {stats['requests']} requests")
    
    print(f"\nResults saved:")
    print(f"All unique names: all_extracted_names.txt ({len(all_names)} names)")
    for endpoint in endpoints_with_limits:
        path = endpoint["path"]
        unique_file = f"unique_names_{path.replace('/', '_')}.txt"
        unique_count = len(unique_by_endpoint[path])
        print(f"Unique names for {path}: {unique_file} ({unique_count} names)")

if __name__ == "__main__":
    main()
