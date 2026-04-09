# Ghost Admin API Reference

## Authentication

Ghost Admin API uses JWT (JSON Web Tokens) for authentication.

```python
import jwt
from datetime import datetime

# API credentials
api_key = "69af3d2ce7384500012e56e1:f79962f8e5adeb18a1d32aff3524261dafb1ce9101bca596e5035d628ab73930"
id, secret = api_key.split(':')

# Create token
iat = int(datetime.now().timestamp())
header = {"alg": "HS256", "kid": id, "typ": "JWT"}
payload = {"iat": iat, "exp": iat + 300, "aud": "/v3/admin/"}
token = jwt.encode(payload, bytes.fromhex(secret), algorithm="HS256", headers=header)
```

## Endpoints

### Posts

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | /ghost/api/admin/posts/ | List posts |
| POST | /ghost/api/admin/posts/ | Create post |
| PUT | /ghost/api/admin/posts/{id}/ | Update post |
| DELETE | /ghost/api/admin/posts/{id}/ | Delete post |

### Images

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | /ghost/api/admin/images/upload/ | Upload image |

### Create Post Example

```python
import requests

headers = {"Authorization": f"Ghost {token}"}
post_data = {
    "posts": [{
        "title": "New Artwork",
        "html": "<p>Body content here</p>",
        "status": "published",
        "feature_image": "https://example.com/image.jpg",
    }]
}
resp = requests.post(
    "https://blog.njohnstonart.com/ghost/api/admin/posts/",
    json=post_data,
    headers=headers,
)
```
