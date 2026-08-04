"""
Blitz Culture — Instagram API test post
----------------------------------------
Posts a single test image + caption to confirm your Graph API setup works
before building the full agent.

SETUP:
1. pip install requests python-dotenv
2. Create a file named `.env` in this same folder (NOT committed to any
   public repo) containing:

    IG_USER_ID=your_instagram_user_id
    IG_ACCESS_TOKEN=your_access_token

3. Host a test image somewhere public (e.g. a GitHub repo's raw URL) and
   paste that URL into TEST_IMAGE_URL below.
4. Run: python test_post.py
"""

import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

IG_USER_ID = os.getenv("IG_USER_ID")
ACCESS_TOKEN = os.getenv("IG_ACCESS_TOKEN")
GRAPH_API_VERSION = "v21.0"
BASE_URL = f"https://graph.instagram.com/{GRAPH_API_VERSION}"

# Replace with a real, publicly-reachable image URL before running
TEST_IMAGE_URL = "https://raw.githubusercontent.com/Austin182538/ff-agent-policy/main/1_wZ1ZJ8xIrLrAxRIXZWvUEA.jpg"
TEST_CAPTION = "Testing the Blitz Culture posting pipeline \U0001F3C8 #fantasyfootball #blitzculture"


def create_media_container(image_url: str, caption: str) -> str:
    """Step 1: tell Instagram to prepare the post (returns a container ID)."""
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }
    resp = requests.post(url, data=payload, timeout=30)
    if not resp.ok:
        print("Instagram API error response:", resp.json())
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"Created media container: {container_id}")
    return container_id


def create_carousel_item(image_url: str) -> str:
    """One carousel slide's container: same /media endpoint as a single
    image post, but flagged is_carousel_item=true and with NO caption --
    Instagram only accepts one caption for the whole carousel, set on the
    parent container in create_carousel_container()."""
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    payload = {
        "image_url": image_url,
        "is_carousel_item": "true",
        "access_token": ACCESS_TOKEN,
    }
    resp = requests.post(url, data=payload, timeout=30)
    if not resp.ok:
        print("Instagram API error response (carousel item):", resp.json())
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"Created carousel item container: {container_id}")
    return container_id


def create_carousel_container(children_ids: list, caption: str) -> str:
    """The parent container tying together every carousel-item container
    (in swipe order) with media_type=CAROUSEL, plus the one caption for the
    whole post. Publish this container's ID with publish_container(), same
    as a single-image post."""
    url = f"{BASE_URL}/{IG_USER_ID}/media"
    payload = {
        "media_type": "CAROUSEL",
        "children": ",".join(children_ids),
        "caption": caption,
        "access_token": ACCESS_TOKEN,
    }
    resp = requests.post(url, data=payload, timeout=30)
    if not resp.ok:
        print("Instagram API error response (carousel container):", resp.json())
    resp.raise_for_status()
    container_id = resp.json()["id"]
    print(f"Created carousel parent container: {container_id}")
    return container_id


def publish_container(container_id: str) -> dict:
    """Step 2: actually publish the prepared container to the feed."""
    url = f"{BASE_URL}/{IG_USER_ID}/media_publish"
    payload = {
        "creation_id": container_id,
        "access_token": ACCESS_TOKEN,
    }
    resp = requests.post(url, data=payload, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    print(f"Published! Media ID: {result.get('id')}")
    return result


def main():
    if not IG_USER_ID or not ACCESS_TOKEN:
        raise SystemExit(
            "Missing IG_USER_ID or IG_ACCESS_TOKEN — check your .env file."
        )

    print("Creating media container...")
    container_id = create_media_container(TEST_IMAGE_URL, TEST_CAPTION)

    # Instagram needs a moment to process the container before it can be
    # published — a short pause avoids a common "media not ready" error.
    print("Waiting a few seconds for Instagram to process the image...")
    time.sleep(5)

    print("Publishing...")
    publish_container(container_id)

    print("Done — check your Instagram account.")


if __name__ == "__main__":
    main()
