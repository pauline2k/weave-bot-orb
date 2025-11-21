import requests
import json

def test_scrape():
    url = "http://localhost:8000/scrape"
    # Using the Oakland Review of Books calendar as a test case since it has events
    target_url = "https://www.oaklandreviewofbooks.org/calendar/"
    
    payload = {
        "url": target_url
    }
    
    print(f"Sending request to {url} with target {target_url}...")
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        
        print(f"Full response: {json.dumps(data, indent=2)}")
        
        for event in data.get('events', []):
            print("-" * 20)
            print(f"Title: {event.get('title')}")
            print(f"Date: {event.get('date')}")
            print(f"Location: {event.get('location')}")
            
    except requests.exceptions.RequestException as e:
        print(f"Error: {e}")
        if hasattr(e, 'response') and e.response is not None:
            print(f"Response content: {e.response.text}")

if __name__ == "__main__":
    test_scrape()
