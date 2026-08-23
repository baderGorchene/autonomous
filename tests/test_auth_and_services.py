def test_register_and_login_owner(client):
    response = client.post("/owners/register", json={
        "name": "Salons de Paris",
        "email": "owner@example.com",
        "phone": "+1234567890",
        "password": "securepassword",
        "business_slug": "salons-paris",
        "language": "en"
    })
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "owner@example.com"

    login_resp = client.post("/owners/token", data={
        "username": "owner@example.com",
        "password": "securepassword"
    })
    assert login_resp.status_code == 200
    assert "access_token" in login_resp.json()
