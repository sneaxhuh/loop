"""A single organizer login for the hackathon workspace."""
import hashlib
import hmac
import secrets
import time
from http.cookies import CookieError, SimpleCookie


class OrganizerAuth:
    def __init__(self, password):
        self.password = password
        self.key = hashlib.sha256(password.encode()).digest()
        self.attempts = {}

    def authenticated(self, cookie_header):
        if not self.password:
            return True
        try:
            cookie = SimpleCookie(cookie_header or "")
            value = cookie["loop_organizer"].value
            payload, signature = value.rsplit(".", 1)
            expected = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
            return hmac.compare_digest(signature, expected) and int(payload.split(".")[0]) > time.time()
        except (KeyError, ValueError, TypeError, CookieError):
            return False

    def login(self, password, address):
        now = time.time()
        self.attempts = {ip: record for ip, record in self.attempts.items() if now - record[0] < 60}
        since, count = self.attempts.get(address, (now, 0))
        if count >= 5:
            return None, "Too many attempts. Try again in a minute."
        self.attempts[address] = (since, count + 1)
        if not isinstance(password, str) or not hmac.compare_digest(password, self.password):
            return None, "That organizer password does not match."
        self.attempts.pop(address, None)
        payload = "%d.%s" % (int(now) + 7 * 86400, secrets.token_hex(16))
        signature = hmac.new(self.key, payload.encode(), hashlib.sha256).hexdigest()
        return payload + "." + signature, None
