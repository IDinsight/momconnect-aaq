import asyncio
import os
import uuid
from datetime import datetime
from typing import Dict, List, Union

import boto3
import pandas as pd
from dateutil import tz
from fastapi.testclient import TestClient
from litellm import embedding
from qdrant_client import QdrantClient
from qdrant_client.models import PointStruct

from core_backend.app.configs.app_config import (
    EMBEDDING_MODEL,
    QDRANT_COLLECTION_NAME,
    QDRANT_N_TOP_SIMILAR,
    QDRANT_VECTOR_SIZE,
    QUESTION_ANSWER_SECRET,
)
from core_backend.app.db.vector_db import (
    create_qdrant_collection,
)
from core_backend.app.schemas import UserQueryBase
from core_backend.app.utils import setup_logger

logger = setup_logger()


class TestRetrievalPerformance:
    def test_retrieval_performance(
        self,
        client: TestClient,
        vectordb_client: QdrantClient,
        validation_data_path: str,
        validation_data_question_col: str,
        validation_data_label_col: str,
        content_data_path: str,
        content_data_label_col: str,
        content_data_text_col: str,
        notification_topic: Union[str, None],
        aws_profile: Union[str, None],
    ) -> None:
        """Test retrieval performance of the system"""
        content_df = self.prepare_content_data(
            content_data_path=content_data_path,
            content_data_label_col=content_data_label_col,
            content_data_text_col=content_data_text_col,
            aws_profile=aws_profile,
        )
        self.load_content_to_qdrant(
            content_dataframe=content_df,
            vectordb_client=vectordb_client,
        )

        val_df = self.generate_retrieval_results(
            client,
            validation_data_path=validation_data_path,
            validation_data_question_col=validation_data_question_col,
            validation_data_label_col=validation_data_label_col,
            aws_profile=aws_profile,
        )

        accuracies = self.get_top_k_accuracies(val_df)

        logger.info("\n" + self.format_accuracies(accuracies))

        if notification_topic is not None:
            message_dict = self._generate_message(
                accuracies,
                validation_data_path=validation_data_path,
                validation_data_label_col=validation_data_label_col,
                validation_data_question_col=validation_data_question_col,
                content_data_path=content_data_path,
                content_data_label_col=content_data_label_col,
                content_data_text_col=content_data_text_col,
            )
            self.send_notification(
                message_dict, topic=notification_topic, aws_profile=aws_profile
            )

    def prepare_content_data(
        self,
        content_data_path: str,
        content_data_label_col: str,
        content_data_text_col: str,
        aws_profile: Union[str, None] = None,
    ) -> pd.DataFrame:
        """Prepare content data for loading to qdrant collection"""
        df = pd.read_csv(
            content_data_path,
            storage_options=dict(profile=aws_profile),
        )
        df["content_id"] = [uuid.uuid4() for _ in range(len(df))]
        df = df.rename(
            columns={
                content_data_label_col: "content_title",
                content_data_text_col: "content_text",
            }
        )
        return df

    def load_content_to_qdrant(
        self,
        content_dataframe: pd.DataFrame,
        vectordb_client: QdrantClient,
    ) -> None:
        """Load content to qdrant collection"""
        # TODO: Update to use a batch upsert API once created
        n_content = content_dataframe.shape[0]
        logger.info(f"Loading {n_content} content item to vector DB...")
        if QDRANT_COLLECTION_NAME not in {
            collection.name
            for collection in vectordb_client.get_collections().collections
        }:
            create_qdrant_collection(QDRANT_COLLECTION_NAME, QDRANT_VECTOR_SIZE)

        embedding_results = embedding(
            EMBEDDING_MODEL, input=content_dataframe["content_text"].tolist()
        )
        content_embeddings = [x["embedding"] for x in embedding_results.data]

        points = [
            PointStruct(
                id=str(content_id),
                vector=content_embedding,
                payload=payload,
            )
            for content_id, content_embedding, payload in zip(
                content_dataframe["content_id"],
                content_embeddings,
                content_dataframe[["content_title", "content_text"]].to_dict("records"),
            )
        ]
        vectordb_client.upsert(
            collection_name=QDRANT_COLLECTION_NAME,
            points=points,
        )
        logger.info(f"Completed loading {n_content} content items to vector DB.")

    def generate_retrieval_results(
        self,
        client: TestClient,
        validation_data_path: str,
        validation_data_question_col: str,
        validation_data_label_col: str,
        aws_profile: Union[str, None] = None,
    ) -> pd.DataFrame:
        """Generate retrieval results for all queries in validation data"""
        df = pd.read_csv(
            validation_data_path,
            storage_options=dict(profile=aws_profile),
        )

        logger.info("Retrieving content for each validation query...")

        df = asyncio.run(
            self.retrieve_results(df, client, validation_data_question_col)
        )

        logger.info("Completed retrieving content for each validation query.")

        def get_rank(row: pd.Series) -> Union[int, None]:
            """Get the rank of label in the retrieved content IDs"""
            label = row[validation_data_label_col]
            ranked_list = row["retrieved_content_titles"]
            try:
                return ranked_list.index(label) + 1
            except ValueError:
                return None

        df["rank"] = df.apply(get_rank, axis=1)
        return df

    async def call_embeddings_search(
        self,
        query_text: str,
        client: TestClient,
    ) -> List[str]:
        """Single POST /embeddings-search request"""
        request_json = UserQueryBase(query_text=query_text).model_dump()
        headers = {"Authorization": f"Bearer {QUESTION_ANSWER_SECRET}"}
        response = client.post("/embeddings-search", json=request_json, headers=headers)
        retrieved = response.json()["content_response"]
        content_titles = [
            retrieved[str(i)]["retrieved_title"] for i in range(len(retrieved))
        ]
        return content_titles

    async def retrieve_results(
        self,
        df: pd.DataFrame,
        client: TestClient,
        validation_data_question_col: str,
    ) -> pd.DataFrame:
        """Asynchronously retrieve similar content for all queries in validation data"""
        tasks = [
            self.call_embeddings_search(query, client)
            for query in df[validation_data_question_col]
        ]
        df["retrieved_content_titles"] = await asyncio.gather(*tasks)
        return df

    @staticmethod
    def get_top_k_accuracies(
        df: pd.DataFrame,
    ) -> List[float]:
        """Get top K accuracy table for validation results"""
        accuracies = []
        for i in range(1, int(QDRANT_N_TOP_SIMILAR) + 1):
            acc = (df["rank"] <= i).mean()
            accuracies.append(acc)
        return accuracies

    @staticmethod
    def format_accuracies(accuracies: List[float]) -> str:
        """Format list of accuracies into readable string"""
        accuracy_message = "\n".join(
            [
                f"   • Top-{i + 1} accuracy: {acc:.1%}"
                for i, acc in enumerate(accuracies)
            ]
        )
        return accuracy_message

    def _generate_message(
        self,
        accuracies: List[float],
        validation_data_path: str,
        validation_data_question_col: str,
        validation_data_label_col: str,
        content_data_path: str,
        content_data_label_col: str,
        content_data_text_col: str,
    ) -> Dict[str, str]:
        """Generate messages for validation results"""
        ist = tz.gettz("Asia/Kolkata")
        timestamp = datetime.now(tz=ist).strftime("%Y-%m-%d %H:%M:%S IST")

        message = (
            f"Content retrieval validation results\n"
            f"--------------------------------------------\n"
            f"\n"
            f"• Timestamp: {timestamp}\n"
            f"• Dataset:\n"
            f"   • Validation data: {validation_data_path}\n"
            f"      • Question column: {validation_data_question_col}\n"
            f"      • Label column: {validation_data_label_col}\n"
            f"   • Content data: {content_data_path}\n"
            f"      • Text column: {content_data_text_col}\n"
            f"      • Label column: {content_data_label_col}\n"
            f"• Embedding model: {EMBEDDING_MODEL}\n"
            f"• Top N accuracies:\n" + self.format_accuracies(accuracies)
        )

        if os.environ.get("GITHUB_ACTIONS") == "true":
            current_branch = os.environ.get("BRANCH_NAME")
            repo_name = os.environ.get("REPO")
            commit = os.environ.get("HASH")

            branch_url = f"https://github.com/{repo_name}/tree/{current_branch}"
            commit_url = f"https://github.com/{repo_name}/commit/{commit}"

            message += (
                f"\n\n"
                f"Repository: {repo_name}\n"
                f"Branch: {current_branch} ({branch_url})\n"
                f"Commit: {commit} ({commit_url})\n"
            )
        else:
            message += "\n\nThis test was run outside of Github Actions."

        return {
            "Subject": f"Retrieval validation results ({timestamp})",
            "Message": message,
        }

    @staticmethod
    def send_notification(
        message_dict: Dict[str, str],
        topic: str,
        aws_profile: Union[str, None] = None,
    ) -> None:
        """
        Function to send notification
        """
        boto3.setup_default_session(profile_name=aws_profile)
        sns = boto3.client("sns")

        sns.publish(
            TopicArn=topic,
            **message_dict,
        )
        print("Successfully sent message to SNS topic")