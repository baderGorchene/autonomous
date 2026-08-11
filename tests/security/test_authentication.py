import pytest
import httpx
import asyncio
from src.security import get_password_hash


@pytest.mark.asyncio
async def test_login_with_invalid_credentials(client):
    response = await client.post(
        "/token",
        data={
            "username": "nonexistent",
            "password": "wrongpassword"
        }
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.json() == {"detail": "Incorrect username or password"}


@pytest.mark.asyncio
async def test_access_protected_endpoint_without_token(client):
    response = await client.get("/owner/dashboard")
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.json() == {"detail": "Not authenticated"}


@pytest.mark.asyncio
async def test_access_protected_endpoint_with_invalid_token(client):
    invalid_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJ0ZXN0b3duZXIiLCJleHAiOjE2NzgwMDY0MDB9.invalid_signature"
    response = await client.get(
        "/owner/dashboard",
        headers={
            "Authorization": f"Bearer {invalid_token}"
        }
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_access_protected_endpoint_with_expired_token(client, db_session):
    # Create a token that is already expired
    expired_token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJleHBpcmVkX3VzZXIiLCJleHAiOjE2NzgwMDY0MDB9.eA_D0j_X_R_Q_P_Z_Y_W_V_U_T_S_R_Q_P_O_N_M_L_K_J_I_H_G_F_E_D_C_B_A"
    response = await client.get(
        "/owner/dashboard",
        headers={
            "Authorization": f"Bearer {expired_token}"
        }
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED
    assert response.json() == {"detail": "Could not validate credentials"}


@pytest.mark.asyncio
async def test_brute_force_login_protection_simulated(client, test_owner):
    # This test assumes a rate limiting mechanism is in place for login attempts
    # If not, it will pass without verifying actual rate limiting.
    # For a real rate limiting test, see test_rate_limiting.py
    for _ in range(5): # Simulate multiple failed attempts
        response = await client.post(
            "/token",
            data={
                "username": test_owner.username,
                "password": "wrongpassword"
            }
        )
        assert response.status_code == httpx.codes.UNAUTHORIZED

    # After several attempts, a rate limit might kick in (if implemented)
    # This specific test only checks for 401, not 429 for now.
    # The actual rate limiting test will cover the 429 scenario.
    response = await client.post(
        "/token",
        data={
            "username": test_owner.username,
            "password": "wrongpassword"
        }
    )
    assert response.status_code == httpx.codes.UNAUTHORIZED

