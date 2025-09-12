import hashlib
import mimetypes
import os
import secrets

from aiobotocore.session import get_session
from logoo import Logger
from tenacity import retry, stop_after_attempt, wait_random, retry_if_not_exception_type


from suggestions.exceptions import InvalidFileType

logger = Logger(__name__)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_random(min=1, max=5),
    retry=retry_if_not_exception_type(ValueError)
    | retry_if_not_exception_type(AssertionError),
    reraise=True,
)
async def upload_file_to_r2(
    *,
    file_name: str,
    file_data: bytes,
    guild_id: int,
    user_id: int,
) -> str:
    """Upload a file to R2 and get the cdn url back"""

    session = get_session()
    async with session.create_client(
        "s3",
        endpoint_url=os.environ["ENDPOINT"],
        aws_access_key_id=os.environ["ACCESS_KEY"],
        aws_secret_access_key=os.environ["SECRET_ACCESS_KEY"],
    ) as client:
        mimetype_guessed, _ = mimetypes.guess_type(file_name)
        accepted_mimetypes: dict[str, set[str]] = {
            "image/jpeg": {"jpeg", "jpg"},
            "image/png": {"png"},
            "image/gif": {"gif"},
            "video/mp3": {"mp3"},
            "video/mp4": {"mp4"},
            "video/mpeg": {"mpeg"},
            "video/webm": {"webm"},
            "image/webp": {"webp"},
            "audio/webp": {"weba"},
        }
        file_names = accepted_mimetypes.get(mimetype_guessed)
        if file_names is None:
            raise InvalidFileType

        for ext in file_names:
            if file_name.endswith(ext):
                break
        else:
            raise InvalidFileType

        file_key = hashlib.sha256(file_data + secrets.token_bytes(16)).hexdigest()
        key = "{}/{}.{}".format(guild_id, file_key, ext)
        await client.put_object(Bucket=os.environ["BUCKET"], Key=key, Body=file_data)
        logger.debug(
            "User %s in guild %s uploaded an image",
            user_id,
            guild_id,
            extra_metadata={
                "author_id": user_id,
                "guild_id": guild_id,
                "original_image_name": file_name,
                "uploaded_to": key,
            },
        )

    return f"https://cdn.suggestions.bot/{key}"
