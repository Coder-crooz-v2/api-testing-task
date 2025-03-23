# Autocomplete API Explorer: Comprehensive Analysis and Name Extraction

## Problem Statement

This project addresses the challenge of efficiently extracting all possible name suggestions from an autocomplete API located at http://35.200.185.69:8000. The API provides name suggestions based on prefix queries but has several important constraints:

1. It has various versions of the autocomplete endpoint
2. It has a specific rate limit at each version's endpoint
3. It returns a limited number of results per query

The goal was to thoroughly understand the API's behavior, document its limitations, and implement an efficient solution to extract all available names while respecting the API's constraints.

## Approach

Implemented solution follows a three-stage approach:

1. **API Discovery and Documentation**: Systematically explore available endpoints and their behaviour
2. **Rate Limit Analysis**: Determine precise rate limits for each endpoint through controlled testing
3. **Optimized Parallel Extraction**: Extract all names using an efficient multi-threaded approach with smart rate limiting

### Stage 1: API Discovery and Documentation

Python scripts were written to discover all available API endpoints and document their behavior:

```python
valid_endpoints = discover_valid_endpoints(base_url)
```

This allowed identification of three primary endpoints:

- `/v1/autocomplete` - The standard endpoint
- `/v2/autocomplete` - A secondary endpoint with different rate limits
- `/v3/autocomplete` - An additional endpoint with yet another rate limit pattern

Each endpoint was thoroughly tested to understand response formats, result patterns, and special behaviors.

### Stage 2: Rate Limit Analysis

A comprehensive rate limit testing approach was developed:

```python
endpoints_with_limits = test_rate_limits(valid_endpoints, base_url)
```

This testing revealed the following rate limits:

- v1: 100 requests per minute
- v2: 50 requests per minute
- v3: 80 requests per minute

### Stage 3: Optimized Parallel Extraction

A multi-threaded solution with smart rate limiting was implemented:

```python
rate_limiter = SmartRateLimiter(endpoints_with_limits)
extractor = NameExtractor(endpoints_with_limits, rate_limiter)
all_names, endpoint_stats, unique_by_endpoint = extractor.extract_names_parallel()
```

The extractor uses several optimizations:

- Parallel processing across endpoints
- Adaptive rate limiting that respects each endpoint's limits
- Intelligent prefix expansion using breadth-first search
- Persistent caching and resumability


## Findings

Detailed analysis revealed several interesting patterns in the API:

1. **API Structure**:
    - The API supports at least three versions (v1, v2, v3)
      - Version 1: http://35.200.185.69:8000/v1/autocomplete
      - Version 2: http://35.200.185.69:8000/v2/autocomplete
      - Version 3: http://35.200.185.69:8000/v3/autocomplete
    - Each endpoint requires a mandatory query parameter with string value, else it returns a status code of 422 (Unprocessed)
    - Each version returns the same format of data and a status code of 200 on success but with different rate limits
    - All endpoints return between 0 to 15 results per query \\
    <br>Example success response:
    ```javascript
    {
      "version": "v1",
      "count": 10,
      "results": [
          "aa",
          "aabdknlvkc",
          "aabrkcd",
          "aadgdqrwdy",
          "aagqg",
          "aaiha",
          "aainmxg",
          "aajfebume",
          "aajwv",
          "aakfubvxv"
        ]
    }
    ````
    <br>Example unprocessed response:
   ```javascript
   {
        "detail": [
            {
                "type": "missing",
                "loc": [
                    "query",
                    "query"
                ],
                "msg": "Field required",
                "input": null
            }
        ]
    }
   ```
3. **Rate Limits**:
    - v1: 100 requests per minute
    - v2: 50 requests per minute
    - v3: 80 requests per minute
    - Rate limits are strictly enforced with 429 status codes when exceeded
    Example rate limit response:
    ```javascript
    {
      "detail": "100 per 1 minute"
    }
    ```
4. **Name Data**:
    - Names always start with the prefix in the query
    - Most names are between 5-12 characters long
    - All names are unique and there is no overlap of names between any endpoint or within the same endpoint for different queries
5. **Extraction Statistics**:
    - Total unique names across all endpoints: 30308 names
    - Total requests made combining all endpoints: 44278 requests
    - Unique names per endpoint:
      - v1: Extracted 17773 unique names in 31954 requests
      - v2: Extracted 7371 unique names in 8632 requests
      - v3: Extracted 5309 unique names in 3692 requests
    - Extraction time: ~5 hours at allowed rates

## Challenges and Solutions

The primary challenge was the sheer volume of names combined with strict rate limits. At 100 requests per minute for the fastest endpoint, extracting all possible names through simple querying would require:

- ~3,000 minutes (50 hours) per endpoint, assuming optimal querying
- ~150 hours total across all endpoints


### The Solution: Parallel Processing with Smart Rate Limiting

To overcome these limitations, the following were carried out:

1. **Implemention of parallel processing across endpoints**:

```python
def extract_names_parallel(self):
    threads = []
    for endpoint in self.endpoints:
        thread = threading.Thread(
            target=self.worker_thread_for_endpoint,
            args=(endpoint, results)
        )
        thread.start()
```

2. **Creation of a sophisticated rate limiter that adapts to API responses**:

```python
class SmartRateLimiter:
    def wait_if_needed(self, path):
        # Rate limiting code
```

3. **Used efficient prefix expansion strategies**:
    - Start with single letters as queries
    - Only expand prefixes that return maximum results
    - Prioritize promising prefix paths
4. **Implemented robust caching and resumability**:
    - Regularly save progress to disk
    - Track which prefixes have been processed
    - Resume extraction from the last saved state if interrupted

### Alternative Methods Considered

1. **Sequential Processing**:
    - Simpler to implement but would take 3x longer (processing one endpoint at a time)
    - Would not utilize the full rate limit capacity of the API
2. **Header Spoofing and Proxy Rotation**:
    - Could potentially increase throughput by making requests appear from different sources
    - Concerns:
        - Potentially violates API Terms of Service
        - Requires maintaining proxy lists
        - Adds complexity with potential for errors
        - Could lead to blacklisting
        - Most proxy providers charge for their service and hence are not a viable solution
3. **Simple Breadth-First Search**:
    - Would work but without optimizations would waste many requests
    - No resumability would mean starting over if interrupted

Parallel processing approach with smart rate limiting was chosen because it:

- Respects API constraints while maximizing throughput
- Provides robust error handling and resumability
- Balances complexity with performance
- Does not attempt to circumvent intended API limitations


## Results and Conclusion

The approach successfully extracted all available names from the autocomplete API while respecting its rate limits. The solution demonstrates how to:

1. Properly explore and document an unknown API
2. Accurately determine rate limits through systematic testing
3. Implement efficient extraction strategies that respect API constraints
4. Utilize parallel processing for optimal throughput

The extracted names are available in the following files:

- `all_extracted_names.txt`: All unique names across all endpoints
- `unique_names_v1_autocomplete.txt`: Names unique to the v1 endpoint
- `unique_names_v2_autocomplete.txt`: Names unique to the v2 endpoint
- `unique_names_v3_autocomplete.txt`: Names unique to the v3 endpoint

## Main script:
The main script for the complete implementation is in the `script.py` file. <br>
Requirements:
```text
python>=3.10 (recommended)
requests==2.32.3
```
