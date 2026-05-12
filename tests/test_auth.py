"""认证模块测试"""
import pytest
from sql_assistant_agent.auth.jwt import create_access_token, hash_password, verify_password


class TestPasswordHashing:
    """测试密码哈希"""

    def test_hash_password(self):
        password = "test1234"
        hashed = hash_password(password)
        assert hashed != password
        assert len(hashed) > 0

    def test_verify_correct_password(self):
        password = "test1234"
        hashed = hash_password(password)
        assert verify_password(password, hashed) is True

    def test_verify_wrong_password(self):
        password = "test1234"
        hashed = hash_password(password)
        assert verify_password("wrong", hashed) is False


class TestJWTToken:
    """测试JWT令牌"""

    def test_create_token(self):
        token = create_access_token(1, "testuser")
        assert isinstance(token, str)
        assert len(token) > 0

    def test_token_contains_claims(self):
        import jwt
        from sql_assistant_agent.config.config import JWT_SECRET, JWT_ALGORITHM

        token = create_access_token(1, "testuser")
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        assert payload["sub"] == "1"
        assert payload["username"] == "testuser"
