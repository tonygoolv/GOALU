import os
import sys
import redis

def test_redis_connection():
    # Retrieve connection details from environment or fallback to default compose service name
    redis_host = os.environ.get("REDIS_HOST", "redis")
    redis_port = int(os.environ.get("REDIS_PORT", 6379))
    
    print(f"Connecting to Redis at {redis_host}:{redis_port}...")
    try:
        # Create a connection client with a 5-second timeout
        r = redis.Redis(host=redis_host, port=redis_port, socket_timeout=5, decode_responses=True)
        
        # Ping the server
        pong = r.ping()
        print(f"Redis Ping: {pong}")
        if not pong:
            raise Exception("Ping returned False")
        
        # Define test key and value
        test_key = "test_bridge_key"
        test_value = "dropship_volatile_success_value"
        
        # Set string key with temporary expiration (10 seconds)
        print(f"Setting key '{test_key}' to value '{test_value}'...")
        r.setex(test_key, 10, test_value)
        
        # Read back key
        retrieved_value = r.get(test_key)
        print(f"Retrieved key '{test_key}': '{retrieved_value}'")
        
        # Verify correctness
        if retrieved_value == test_value:
            print("SUCCESS: Redis set and get verified. Docker network bridge is working properly.")
            sys.exit(0)
        else:
            print(f"FAILURE: Retrieved value '{retrieved_value}' does not match expected '{test_value}'.")
            sys.exit(1)
            
    except redis.exceptions.ConnectionError as ce:
        print(f"FAILURE: Could not connect to Redis at {redis_host}:{redis_port}. ConnectionError: {ce}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"FAILURE: An unexpected error occurred: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    test_redis_connection()
