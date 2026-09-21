from tests.conftest import auth_header


def test_register_company_creates_hr_admin(client, mock_clerk_user):
    mock_clerk_user("clerk_user_1")

    response = client.post(
        "/api/v1/auth/register-company",
        json={"company_name": "Acme Corp", "name": "Jane HR", "email": "jane@acme.com"},
        headers=auth_header(),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["role"] == "HR_ADMIN"
    assert body["name"] == "Jane HR"
    assert body["email"] == "jane@acme.com"
    assert body["clerk_user_id"] == "clerk_user_1"


def test_register_company_twice_for_same_identity_conflicts(client, mock_clerk_user):
    mock_clerk_user("clerk_user_2")

    first = client.post(
        "/api/v1/auth/register-company",
        json={"company_name": "Beta Inc", "name": "Bob HR", "email": "bob@beta.com"},
        headers=auth_header(),
    )
    assert first.status_code == 200

    second = client.post(
        "/api/v1/auth/register-company",
        json={"company_name": "Beta Inc Again", "name": "Bob HR", "email": "bob@beta.com"},
        headers=auth_header(),
    )
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "CONFLICT"


def test_get_me_returns_profile_after_registration(client, mock_clerk_user):
    mock_clerk_user("clerk_user_3")

    client.post(
        "/api/v1/auth/register-company",
        json={"company_name": "Gamma LLC", "name": "Cara HR", "email": "cara@gamma.com"},
        headers=auth_header(),
    )

    me = client.get("/api/v1/me", headers=auth_header())
    assert me.status_code == 200
    assert me.json()["email"] == "cara@gamma.com"
    assert me.json()["role"] == "HR_ADMIN"


def test_get_me_without_provisioned_account_is_unauthorized(client, mock_clerk_user):
    mock_clerk_user("clerk_never_registered")

    response = client.get("/api/v1/me", headers=auth_header())
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "UNAUTHORIZED"


def test_get_me_without_token_is_unauthorized(client):
    response = client.get("/api/v1/me")
    assert response.status_code == 401
