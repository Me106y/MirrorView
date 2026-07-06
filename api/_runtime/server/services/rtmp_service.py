import hashlib
import time

class RTMPService:
    def __init__(self, base_url):
        self.base_url = base_url

    def generate_push_url(self, interview_id, user_id):
        """
        Generate a unique RTMP push URL for the interview.
        """
        # stream_key = f"interview_{interview_id}_{user_id}_{int(time.time())}"
        # return f"{self.base_url}/{stream_key}"
        return "rtmp://116.62.11.13:1935/live/test"

    def generate_play_url(self, push_url):
        """
        Generate the playback URL corresponding to the push URL.
        """
        # In this simple setup, play URL is the same as push URL
        # In real scenarios (e.g. CDN), it might differ.
        return push_url
