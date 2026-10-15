from key_value.aio.stores.firestore.store import FirestoreV1KeySanitizationStrategy


def test_url_client_ids_become_valid_firestore_ids():
    # claude.ai 는 OAuth 클라이언트 ID 로 URL 을 쓴다 (CIMD). Firestore 문서 ID 에는 '/' 가 들어갈 수 없다.
    key = "https://claude.ai/oauth/mcp-oauth-client-metadata"
    out = FirestoreV1KeySanitizationStrategy().sanitize(key)
    assert "/" not in out
    assert out != FirestoreV1KeySanitizationStrategy().sanitize(key + "x")
