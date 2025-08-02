from aiohttp import web
import asyncio
import aiofiles
from pathlib import Path
import logging
import argparse
import os


def get_config():
    parser = argparse.ArgumentParser(description='Микросервис для загрузки архивов фотографий')

    parser.add_argument('--photos-dir',
                       default=os.getenv('PHOTOS_DIR', 'test_photos'),
                       help='Путь к каталогу с фотографиями (env: PHOTOS_DIR)')
    parser.add_argument('--enable-logging',
                       action='store_true',
                       default=os.getenv('ENABLE_LOGGING', 'true').lower() == 'true',
                       help='Включить логирование (env: ENABLE_LOGGING)')
    parser.add_argument('--response-delay',
                       type=float,
                       default=float(os.getenv('RESPONSE_DELAY', '9')),
                       help='Задержка ответа в секундах (env: RESPONSE_DELAY)')

    return parser.parse_args()


config = get_config()


logging.basicConfig(
    level=logging.DEBUG if config.enable_logging else logging.CRITICAL,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def archive(request):
    archive_hash = request.match_info['archive_hash']
    source_dir = Path(config.photos_dir) / archive_hash

    if not source_dir.exists() or not source_dir.is_dir():
        logger.error(f"Архив не найден: {archive_hash}")
        return web.Response(
            text="Архив не существует или был удален",
            status=404,
            content_type='text/plain'
        )

    logger.info(f"Подготовка архива для: {archive_hash}")

    process = await asyncio.create_subprocess_exec(
        'zip', '-r', '-', str(source_dir),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )

    response = web.StreamResponse(
        status=200,
        headers={
            'Content-Type': 'application/zip',
            'Content-Disposition': 'attachment; filename="photo_archive.zip"'
        }
    )

    try:
        await response.prepare(request)

        while True:
            chunk = await process.stdout.read(1024 * 1024)
            if not chunk:
                break
            await response.write(chunk)
            await asyncio.sleep(config.response_delay)

    except (ConnectionResetError, asyncio.CancelledError):
        logger.debug("Загрузка прервана - завершение процесса zip")
        raise

    except Exception as e:
        logger.error(f"Ошибка при создании архива: {str(e)}")
        raise web.HTTPInternalServerError()

    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    return response


async def handle_index_page(request):
    async with aiofiles.open('index.html', mode='r') as index_file:
        index_contents = await index_file.read()
    return web.Response(text=index_contents, content_type='text/html')


if __name__ == '__main__':
    app = web.Application()
    app.add_routes([
        web.get('/', handle_index_page),
        web.get('/archive/{archive_hash}/', archive),
    ])
    web.run_app(app)