import os
import time
from functools import partial
from io import BytesIO
from typing import Any, Dict, List

import pytest
from fastapi.testclient import TestClient

from core_backend.app.llm_call.llm_prompts import AlignmentScore, IdentifiedLanguage
from core_backend.app.llm_call.process_input import (
    _classify_safety,
    _identify_language,
    _translate_question,
)
from core_backend.app.llm_call.process_output import _check_align_score
from core_backend.app.question_answer.config import N_TOP_CONTENT
from core_backend.app.question_answer.schemas import (
    ErrorType,
    QueryRefined,
    QueryResponse,
    QueryResponseError,
    QuerySearchResult,
)
from core_backend.app.question_answer.utils import (
    get_context_string_from_search_results,
)
from core_backend.tests.api.conftest import (
    TEST_USERNAME,
    TEST_USERNAME_2,
)


class TestApiCallQuota:

    @pytest.mark.parametrize(
        "temp_user_api_key_and_api_quota",
        [
            {"username": "temp_user_llm_api_limit_0", "api_daily_quota": 0},
            {"username": "temp_user_llm_api_limit_2", "api_daily_quota": 2},
            {"username": "temp_user_llm_api_limit_5", "api_daily_quota": 5},
        ],
        indirect=True,
    )
    async def test_api_call_llm_quota_integer(
        self,
        client: TestClient,
        temp_user_api_key_and_api_quota: tuple[str, int],
    ) -> None:
        temp_api_key, api_daily_limit = temp_user_api_key_and_api_quota

        for _i in range(api_daily_limit):
            response = client.post(
                "/search",
                json={
                    "query_text": "Test question",
                    "generate_llm_response": False,
                },
                headers={"Authorization": f"Bearer {temp_api_key}"},
            )
            assert response.status_code == 200
        response = client.post(
            "/search",
            json={
                "query_text": "Test question",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {temp_api_key}"},
        )
        assert response.status_code == 429

    @pytest.mark.parametrize(
        "temp_user_api_key_and_api_quota",
        [
            {"username": "temp_user_emb_api_limit_0", "api_daily_quota": 0},
            {"username": "temp_user_emb_api_limit_2", "api_daily_quota": 2},
            {"username": "temp_user_emb_api_limit_5", "api_daily_quota": 5},
        ],
        indirect=True,
    )
    async def test_api_call_embeddings_quota_integer(
        self,
        client: TestClient,
        temp_user_api_key_and_api_quota: tuple[str, int],
    ) -> None:
        temp_api_key, api_daily_limit = temp_user_api_key_and_api_quota

        for _i in range(api_daily_limit):
            response = client.post(
                "/search",
                json={
                    "query_text": "Test question",
                    "generate_llm_response": False,
                },
                headers={"Authorization": f"Bearer {temp_api_key}"},
            )
            assert response.status_code == 200
        response = client.post(
            "/search",
            json={
                "query_text": "Test question",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {temp_api_key}"},
        )
        assert response.status_code == 429

    @pytest.mark.parametrize(
        "temp_user_api_key_and_api_quota",
        [
            {"username": "temp_user_mix_api_limit_0", "api_daily_quota": 0},
            {"username": "temp_user_mix_api_limit_2", "api_daily_quota": 2},
            {"username": "temp_user_mix_api_limit_5", "api_daily_quota": 5},
        ],
        indirect=True,
    )
    async def test_api_call_mix_quota_integer(
        self,
        client: TestClient,
        temp_user_api_key_and_api_quota: tuple[str, int],
    ) -> None:
        temp_api_key, api_daily_limit = temp_user_api_key_and_api_quota

        for i in range(api_daily_limit):
            if i // 2 == 0:
                response = client.post(
                    "/search",
                    json={
                        "query_text": "Test question",
                        "generate_llm_response": True,
                    },
                    headers={"Authorization": f"Bearer {temp_api_key}"},
                )
            else:
                response = client.post(
                    "/search",
                    json={
                        "query_text": "Test question",
                        "generate_llm_response": False,
                    },
                    headers={"Authorization": f"Bearer {temp_api_key}"},
                )
            assert response.status_code == 200
        if api_daily_limit % 2 == 0:
            response = client.post(
                "/search",
                json={
                    "query_text": "Test question",
                    "generate_llm_response": True,
                },
                headers={"Authorization": f"Bearer {temp_api_key}"},
            )
        else:
            response = client.post(
                "/search",
                json={
                    "query_text": "Test question",
                    "generate_llm_response": False,
                },
                headers={"Authorization": f"Bearer {temp_api_key}"},
            )
        assert response.status_code == 429

    @pytest.mark.parametrize(
        "temp_user_api_key_and_api_quota",
        [{"username": "temp_user_api_unlimited", "api_daily_quota": None}],
        indirect=True,
    )
    async def test_api_quota_unlimited(
        self,
        client: TestClient,
        temp_user_api_key_and_api_quota: tuple[str, int],
    ) -> None:
        temp_api_key, _ = temp_user_api_key_and_api_quota

        response = client.post(
            "/search",
            json={
                "query_text": "Tell me about a good sport to play",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {temp_api_key}"},
        )
        assert response.status_code == 200


class TestEmbeddingsSearch:
    @pytest.mark.parametrize(
        "token, expected_status_code",
        [
            ("api_key_incorrect", 401),
            ("api_key_correct", 200),
        ],
    )
    def test_search_results(
        self,
        token: str,
        expected_status_code: int,
        client: TestClient,
        api_key_user1: str,
        fullaccess_token: str,
        faq_contents: pytest.FixtureRequest,
    ) -> None:
        while True:
            response = client.get(
                "/content",
                headers={"Authorization": f"Bearer {fullaccess_token}"},
            )
            time.sleep(2)
            if len(response.json()) == 9:
                break

        request_token = api_key_user1 if token == "api_key_correct" else token
        response = client.post(
            "/search",
            json={
                "query_text": "Tell me about a good sport to play",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {request_token}"},
        )
        assert response.status_code == expected_status_code

        if expected_status_code == 200:
            json_search_results = response.json()["search_results"]
            assert len(json_search_results.keys()) == int(N_TOP_CONTENT)

    @pytest.fixture
    def question_response(
        self, client: TestClient, api_key_user1: str
    ) -> QueryResponse:
        response = client.post(
            "/search",
            json={
                "query_text": "Tell me about a good sport to play",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        return response.json()

    @pytest.mark.parametrize(
        "outcome, expected_status_code, endpoint",
        [
            ("incorrect", 401, "/response-feedback"),
            ("correct", 200, "/response-feedback"),
            ("incorrect", 401, "/content-feedback"),
            ("correct", 200, "/content-feedback"),
        ],
    )
    def test_response_feedback_correct_token(
        self,
        outcome: str,
        expected_status_code: int,
        endpoint: str,
        api_key_user1: str,
        client: TestClient,
        question_response: Dict[str, Any],
        faq_contents: List[int],
    ) -> None:
        query_id = question_response["query_id"]
        feedback_secret_key = question_response["feedback_secret_key"]
        token = api_key_user1 if outcome == "correct" else "api_key_incorrect"
        json = {
            "feedback_text": "This is feedback",
            "query_id": query_id,
            "feedback_sentiment": "positive",
            "feedback_secret_key": feedback_secret_key,
        }

        if endpoint == "/content-feedback":
            json["content_id"] = faq_contents[0]

        response = client.post(
            endpoint,
            json=json,
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == expected_status_code

    @pytest.mark.parametrize("endpoint", ["/response-feedback", "/content-feedback"])
    def test_response_feedback_incorrect_secret(
        self,
        endpoint: str,
        client: TestClient,
        api_key_user1: str,
        question_response: Dict[str, Any],
    ) -> None:
        query_id = question_response["query_id"]

        json = {
            "feedback_text": "This feedback has the wrong secret key",
            "query_id": query_id,
            "feedback_secret_key": "incorrect_key",
        }

        if endpoint == "/content-feedback":
            json["content_id"] = 1

        response = client.post(
            endpoint,
            json=json,
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("endpoint", ["/response-feedback", "/content-feedback"])
    async def test_response_feedback_incorrect_query_id(
        self,
        endpoint: str,
        client: TestClient,
        api_key_user1: str,
        question_response: Dict[str, Any],
    ) -> None:
        feedback_secret_key = question_response["feedback_secret_key"]
        json = {
            "feedback_text": "This feedback has the wrong query id",
            "query_id": 99999,
            "feedback_secret_key": feedback_secret_key,
        }
        if endpoint == "/content-feedback":
            json["content_id"] = 1

        response = client.post(
            endpoint,
            json=json,
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        assert response.status_code == 400

    @pytest.mark.parametrize("endpoint", ["/response-feedback", "/content-feedback"])
    async def test_response_feedback_incorrect_sentiment(
        self,
        endpoint: str,
        client: TestClient,
        api_key_user1: str,
        question_response: Dict[str, Any],
    ) -> None:
        query_id = question_response["query_id"]
        feedback_secret_key = question_response["feedback_secret_key"]

        json = {
            "feedback_text": "This feedback has the wrong sentiment",
            "query_id": query_id,
            "feedback_sentiment": "incorrect",
            "feedback_secret_key": feedback_secret_key,
        }

        if endpoint == "/content-feedback":
            json["content_id"] = 1

        response = client.post(
            endpoint,
            json=json,
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        assert response.status_code == 422

    @pytest.mark.parametrize("endpoint", ["/response-feedback", "/content-feedback"])
    async def test_response_feedback_sentiment_only(
        self,
        endpoint: str,
        client: TestClient,
        api_key_user1: str,
        faq_contents: List[int],
        question_response: Dict[str, Any],
    ) -> None:
        query_id = question_response["query_id"]
        feedback_secret_key = question_response["feedback_secret_key"]

        json = {
            "query_id": query_id,
            "feedback_sentiment": "positive",
            "feedback_secret_key": feedback_secret_key,
        }
        if endpoint == "/content-feedback":
            json["content_id"] = faq_contents[0]

        response = client.post(
            endpoint,
            json=json,
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        assert response.status_code == 200

    @pytest.mark.parametrize(
        "username, expect_found",
        [
            (TEST_USERNAME, True),
            (TEST_USERNAME_2, False),
        ],
    )
    def test_user2_access_user1_content(
        self,
        client: TestClient,
        username: str,
        api_key_user1: str,
        api_key_user2: str,
        expect_found: bool,
        fullaccess_token: str,
        faq_contents: List[int],
    ) -> None:
        token = api_key_user1 if username == TEST_USERNAME else api_key_user2
        while True:
            response = client.get(
                "/content",
                headers={"Authorization": f"Bearer {fullaccess_token}"},
            )
            time.sleep(2)
            if len(response.json()) == 9:
                break
        response = client.post(
            "/search",
            json={
                "query_text": "Tell me about camping",
                "generate_llm_response": False,
            },
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        if response.status_code == 200:
            all_retireved_content_ids = [
                value["id"] for value in response.json()["search_results"].values()
            ]
            if expect_found:
                # user1 has contents in DB uploaded by the faq_contents fixture
                assert len(all_retireved_content_ids) > 0
            else:
                # user2 should not have any content
                assert len(all_retireved_content_ids) == 0

    @pytest.mark.parametrize(
        "content_id_valid, response_code", ([True, 200], [False, 400])
    )
    def test_content_feedback_check_content_id(
        self,
        content_id_valid: str,
        response_code: int,
        client: TestClient,
        api_key_user1: str,
        question_response: Dict[str, Any],
        faq_contents: List[int],
    ) -> None:
        query_id = question_response["query_id"]
        feedback_secret_key = question_response["feedback_secret_key"]

        if content_id_valid:
            content_id = faq_contents[0]
        else:
            content_id = 99999

        response = client.post(
            "/content-feedback",
            json={
                "query_id": query_id,
                "content_id": content_id,
                "feedback_text": "This feedback has the wrong content id",
                "feedback_sentiment": "positive",
                "feedback_secret_key": feedback_secret_key,
            },
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )

        assert response.status_code == response_code


class TestGenerateResponse:

    @pytest.mark.parametrize(
        "username, expect_found",
        [
            (TEST_USERNAME, True),
            (TEST_USERNAME_2, False),
        ],
    )
    def test_user2_access_user1_content(
        self,
        client: TestClient,
        username: str,
        api_key_user1: str,
        api_key_user2: str,
        expect_found: bool,
        faq_contents: List[int],
    ) -> None:
        token = api_key_user1 if username == TEST_USERNAME else api_key_user2
        response = client.post(
            "/search",
            json={"query_text": "Tell me about camping", "generate_llm_response": True},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert response.status_code == 200

        if response.status_code == 200:
            all_retireved_content_ids = [
                value["id"] for value in response.json()["search_results"].values()
            ]
            if expect_found:
                # user1 has contents in DB uploaded by the faq_contents fixture
                assert len(all_retireved_content_ids) > 0
            else:
                # user2 should not have any content
                assert len(all_retireved_content_ids) == 0

    @pytest.mark.parametrize(
        "query_text, status_code",
        [
            ("how do i get rid of this back pain?", 200),
            ("hello world", 200),
            ("hello world!", 200),
            ("This is a test!!!", 200),
            ("supercalifragilisticexpialidocious", 200),
            ("normal text", 200),
            ("is this gibberish?", 200),
            ("i have a backache", 200),
            (" h e l l o ", 200),
            ("!@#$!@", 400),
            ("!!!!????", 400),
            ("12345", 400),
            ("R2D2 & C3PO", 400),
            ("h3ll0 w0rld", 400),
            ("thequickbrownfox", 400),
            ("asdfasdfasdf", 400),
            ("zxcvwerjasc", 400),
            ("nmnjcviburili,<>", 400),
            ("zxcvnadtruqe", 400),
            ("ertrjiloifdfyyoiu", 400),
            ("grty iuewdiivjh", 400),
            ("@&$+_", 400),
            ("hfnoseth", 400),
            ("asdfads", 400),
        ],
    )
    def test_gibberish_text(
        self, api_key_user1: str, client: TestClient, query_text: str, status_code: int
    ) -> None:
        response = client.post(
            "/search",
            json={"query_text": query_text},
            headers={"Authorization": f"Bearer {api_key_user1}"},
        )
        assert response.status_code == status_code


class TestSTTResponse:
    @pytest.mark.parametrize(
        "is_authorized, expected_status_code, mock_response",
        [
            (True, 200, {"text": "Paris"}),
            (False, 401, {"error": "Unauthorized"}),
            (True, 400, {"text": "Paris"}),
            (True, 500, {}),
        ],
    )
    def test_voice_search(
        self,
        is_authorized: bool,
        expected_status_code: int,
        mock_response: dict,
        client: TestClient,
        monkeypatch: pytest.MonkeyPatch,
        api_key_user1: str,
    ) -> None:
        token = api_key_user1 if is_authorized else "api_key_incorrect"

        async def dummy_download_file_from_url(
            file_url: str,
        ) -> tuple[BytesIO, str, str]:

            return BytesIO(b"fake audio content"), "audio/mpeg", "mp3"

        async def dummy_post_to_speech_stt(file_path: str, endpoint_url: str) -> dict:
            if expected_status_code == 500:
                raise ValueError("Error from CUSTOM_STT_ENDPOINT")
            return mock_response

        async def dummy_post_to_speech_tts(
            text: str, endpoint_url: str, language: str
        ) -> BytesIO:
            if expected_status_code == 400:
                raise ValueError("Error from CUSTOM_TTS_ENDPOINT")
            return BytesIO(b"fake audio content")

        async def async_fake_transcribe_audio(*args: Any, **kwargs: Any) -> str:
            if expected_status_code == 500:
                raise ValueError("Error from External STT service")
            return "transcribed text"

        async def async_fake_generate_tts_on_gcs(*args: Any, **kwargs: Any) -> BytesIO:
            if expected_status_code == 400:
                raise ValueError("Error from External TTS service")
            return BytesIO(b"fake audio content")

        monkeypatch.setattr(
            "core_backend.app.question_answer.routers.transcribe_audio",
            async_fake_transcribe_audio,
        )
        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output.synthesize_speech",
            async_fake_generate_tts_on_gcs,
        )
        monkeypatch.setattr(
            "core_backend.app.question_answer.routers.post_to_speech_stt",
            dummy_post_to_speech_stt,
        )
        monkeypatch.setattr(
            "core_backend.app.question_answer.routers.download_file_from_url",
            dummy_download_file_from_url,
        )
        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output.post_to_internal_tts",
            dummy_post_to_speech_tts,
        )

        temp_dir = "temp"
        os.makedirs(temp_dir, exist_ok=True)

        file_url = "http://example.com/test.mp3"

        response = client.post(
            "/voice-search",
            headers={"Authorization": f"Bearer {token}"},
            params={"file_url": file_url},
        )

        assert response.status_code == expected_status_code

        if expected_status_code == 200:
            json_response = response.json()
            assert "llm_response" in json_response
            assert "tts_filepath" in json_response

        elif expected_status_code == 500:
            json_response = response.json()
            assert "error" in json_response

        elif expected_status_code == 400:
            json_response = response.json()
            assert "error_message" in json_response

        if os.path.exists(temp_dir):
            for file_name in os.listdir(temp_dir):
                file_path = os.path.join(temp_dir, file_name)
                if os.path.isfile(file_path):
                    os.remove(file_path)
            os.rmdir(temp_dir)


class TestErrorResponses:
    SUPPORTED_LANGUAGE = IdentifiedLanguage.get_supported_languages()[-1]

    @pytest.fixture
    def user_query_response(
        self,
    ) -> QueryResponse:
        return QueryResponse(
            query_id=124,
            search_results={},
            llm_response=None,
            feedback_secret_key="abc123",
            debug_info={},
        )

    @pytest.fixture
    def user_query_refined(self, request: pytest.FixtureRequest) -> QueryRefined:
        if hasattr(request, "param"):
            language = request.param
        else:
            language = None
        return QueryRefined(
            query_text="This is a basic query",
            user_id=124,
            original_language=language,
            query_text_original="This is a query original",
        )

    @pytest.mark.parametrize(
        "identified_lang_str,should_error,expected_error_type",
        [
            ("ENGLISH", False, None),
            ("HINDI", False, None),
            ("UNINTELLIGIBLE", True, ErrorType.UNINTELLIGIBLE_INPUT),
            ("GIBBERISH", True, ErrorType.UNSUPPORTED_LANGUAGE),
            ("UNSUPPORTED", True, ErrorType.UNSUPPORTED_LANGUAGE),
            ("SOME_UNSUPPORTED_LANG", True, ErrorType.UNSUPPORTED_LANGUAGE),
            ("don't kow", True, ErrorType.UNSUPPORTED_LANGUAGE),
        ],
    )
    async def test_language_identify_error(
        self,
        user_query_response: QueryResponse,
        identified_lang_str: str,
        should_error: bool,
        expected_error_type: ErrorType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        user_query_refined = QueryRefined(
            query_text="This is a basic query",
            user_id=124,
            original_language=None,
            query_text_original="This is a query original",
        )

        async def mock_ask_llm(*args: Any, **kwargs: Any) -> str:
            return identified_lang_str

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_input._ask_llm_async", mock_ask_llm
        )

        query, response = await _identify_language(
            user_query_refined, user_query_response
        )
        if should_error:
            assert isinstance(response, QueryResponseError)
            assert response.error_type == expected_error_type
        else:
            assert isinstance(response, QueryResponse)
            assert query.original_language == getattr(
                IdentifiedLanguage, identified_lang_str
            )

    @pytest.mark.parametrize(
        "user_query_refined,should_error,expected_error_type",
        [
            ("ENGLISH", False, None),
            (SUPPORTED_LANGUAGE, False, None),
        ],
        indirect=["user_query_refined"],
    )
    async def test_translate_error(
        self,
        user_query_refined: QueryRefined,
        user_query_response: QueryResponse,
        should_error: bool,
        expected_error_type: ErrorType,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def mock_ask_llm(*args: Any, **kwargs: Any) -> str:
            return "This is a translated LLM response"

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_input._ask_llm_async", mock_ask_llm
        )
        query, response = await _translate_question(
            user_query_refined, user_query_response
        )
        if should_error:
            assert isinstance(response, QueryResponseError)
            assert response.error_type == expected_error_type
        else:
            assert isinstance(response, QueryResponse)
            if query.original_language == "ENGLISH":
                assert query.query_text == "This is a basic query"
            else:
                assert query.query_text == "This is a translated LLM response"

    async def test_translate_before_language_id_errors(
        self,
        user_query_response: QueryResponse,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        async def mock_ask_llm(*args: Any, **kwargs: Any) -> str:
            return "This is a translated LLM response"

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_input._ask_llm_async", mock_ask_llm
        )

        user_query_refined = QueryRefined(
            query_text="This is a basic query",
            user_id=124,
            original_language=None,
            query_text_original="This is a query original",
        )
        with pytest.raises(ValueError):
            query, response = await _translate_question(
                user_query_refined, user_query_response
            )

    @pytest.mark.parametrize(
        "classification, should_error",
        [("SAFE", False), ("INAPPROPRIATE_LANGUAGE", True), ("PROMPT_INJECTION", True)],
    )
    async def test_unsafe_query_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        user_query_refined: QueryRefined,
        user_query_response: QueryResponse,
        classification: str,
        should_error: bool,
    ) -> None:
        async def mock_ask_llm(llm_response: str, *args: Any, **kwargs: Any) -> str:
            return llm_response

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_input._ask_llm_async",
            partial(mock_ask_llm, classification),
        )
        query, response = await _classify_safety(
            user_query_refined, user_query_response
        )

        if should_error:
            assert isinstance(response, QueryResponseError)
            assert response.error_type == ErrorType.QUERY_UNSAFE
        else:
            assert isinstance(response, QueryResponse)
            assert query.query_text == "This is a basic query"


class TestAlignScore:
    @pytest.fixture
    def user_query_response(self) -> QueryResponse:
        return QueryResponse(
            query_id=124,
            search_results={
                1: QuerySearchResult(
                    title="World",
                    text="hello world",
                    id=1,
                    distance=0.2,
                ),
                2: QuerySearchResult(
                    title="Universe",
                    text="goodbye universe",
                    id=2,
                    distance=0.2,
                ),
            },
            llm_response="This is a response",
            feedback_secret_key="abc123",
            debug_info={},
        )

    async def test_score_less_than_threshold(
        self, user_query_response: QueryResponse, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def mock_get_align_score(*args: Any, **kwargs: Any) -> AlignmentScore:
            return AlignmentScore(score=0.2, reason="test - low score")

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output._get_llm_align_score",
            mock_get_align_score,
        )
        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output.ALIGN_SCORE_THRESHOLD",
            0.7,
        )
        update_query_response = await _check_align_score(user_query_response)
        assert isinstance(update_query_response, QueryResponse)
        assert update_query_response.debug_info["factual_consistency"]["score"] == 0.2
        assert update_query_response.llm_response is None

    async def test_score_greater_than_threshold(
        self, user_query_response: QueryResponse, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        async def mock_get_align_score(*args: Any, **kwargs: Any) -> AlignmentScore:
            return AlignmentScore(score=0.9, reason="test - high score")

        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output.ALIGN_SCORE_THRESHOLD",
            0.7,
        )
        monkeypatch.setattr(
            "core_backend.app.llm_call.process_output._get_llm_align_score",
            mock_get_align_score,
        )
        update_query_response = await _check_align_score(user_query_response)
        assert isinstance(update_query_response, QueryResponse)
        assert update_query_response.debug_info["factual_consistency"]["score"] == 0.9

    async def test_get_context_string_from_search_results(
        self, user_query_response: QueryResponse
    ) -> None:
        assert user_query_response.search_results is not None  # Type assertion for mypy

        context_string = get_context_string_from_search_results(
            user_query_response.search_results
        )

        expected_context_string = (
            "1. World\nhello world\n\n2. Universe\ngoodbye universe"
        )
        assert context_string == expected_context_string
