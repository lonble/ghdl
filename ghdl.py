#!/usr/bin/env python3

import urllib.request
import urllib.error
import pathlib
import json
import re
import logging
import threading
import concurrent.futures
import traceback
import argparse
import signal


_CHUNK_SIZE = 4096
_URL_TIMEOUT = 3
_DEFAULT_CONCURRENCY = 5
_DEFAULT_LOG_LEVEL = logging.WARNING
_PROG_NAME = "ghdl"

logger = logging.getLogger(_PROG_NAME if __name__ == "__main__" else __name__)
_log_handler = logging.StreamHandler()
_log_handler.setLevel(logging.DEBUG)
_log_handler.setFormatter(logging.Formatter("%(levelname)s:%(name)s:%(message)s"))
logger.addHandler(_log_handler)


def _get_headers(token: str = "") -> dict[str, str]:
    if token:
        return {"Authorization": f"Bearer {token}"}
    else:
        return {}


def _get_latest_release(
    owner: str, repo: str, token: str = "", interrupt: threading.Event | None = None
) -> dict | None:
    try:
        success = False
        logger.debug(f'Start to get latest release of repo "{owner}/{repo}"')
        try:
            url = f"https://api.github.com/repos/{owner}/{repo}/releases/latest"
            request = urllib.request.Request(url, headers=_get_headers(token))
            with urllib.request.urlopen(request, timeout=_URL_TIMEOUT) as resoonse:
                data = json.load(resoonse)
                success = True
                return data
        except ValueError as e:
            logger.warning(f'ValueError of repo "{owner}/{repo}": {e}')
        except urllib.error.HTTPError as e:
            logger.warning(f'HTTPError of repo "{owner}/{repo}": {e.code} {e.reason}')
        except urllib.error.URLError as e:
            logger.warning(f'URLError of repo "{owner}/{repo}": {e.reason}')
        except ConnectionError as e:
            logger.warning(
                f'ConnectionError of repo "{owner}/{repo}": {e.strerror if e.strerror else e}'
            )
        except OSError as e:
            logger.warning(
                f'OSError of repo "{owner}/{repo}": {e.strerror if e.strerror else e}'
            )
        except KeyboardInterrupt:
            logger.warning(f'KeyboardInterrupt of repo "{owner}/{repo}"')
            # This exception only occurs in non-concurrent case
            raise
        finally:
            if success:
                logger.info(
                    f'Fetched latest release of repo "{owner}/{repo}", release name: "{data["name"]}"'
                )
            else:
                logger.warning(f'Failed to get latest release of repo "{owner}/{repo}"')
    except:
        if interrupt:
            traceback.print_exc()
        else:
            raise


def _download_asset(
    url: str,
    filename: str,
    dir: str = "",
    token: str = "",
    interrupt: threading.Event | None = None,
) -> bool:
    try:
        file_opened = False
        success = False
        logger.debug(f'Start to download file "{filename}"')
        try:
            saved_path = pathlib.Path(dir) / filename
            request = urllib.request.Request(url, headers=_get_headers(token))
            with urllib.request.urlopen(request, timeout=_URL_TIMEOUT) as response:
                content_length = int(response.getheader("Content-Length"))
                with saved_path.open("wb") as file:
                    file_opened = True
                    downloaded_size = 0
                    while True:
                        if interrupt and interrupt.is_set():
                            raise KeyboardInterrupt
                        chunk = response.read(_CHUNK_SIZE)
                        if chunk:
                            file.write(chunk)
                            downloaded_size += len(chunk)
                        else:
                            break
                    if downloaded_size == content_length:
                        success = True
        except ValueError as e:
            logger.warning(f'ValueError of file "{filename}": {e}')
        except urllib.error.URLError as e:
            logger.warning(f'URLError of file "{filename}": {e.reason}')
        except ConnectionError as e:
            logger.warning(
                f'ConnectionError of file "{filename}": {e.strerror if e.strerror else e}'
            )
        except OSError as e:
            logger.warning(
                f'OSError of file "{filename}": {e.strerror if e.strerror else e}'
            )
        except KeyboardInterrupt:
            logger.warning(f'KeyboardInterrupt of file "{filename}"')
            if not interrupt:
                raise
        finally:
            if file_opened and not success:
                logger.warning(
                    f'Failed to download file completely, deleting file "{filename}"'
                )
                saved_path.unlink(missing_ok=True)
            if success:
                logger.info(f'Downloaded File: "{filename}"')
            else:
                logger.warning(f'Failed to download file "{filename}"')
        return success
    except:
        if interrupt:
            traceback.print_exc()
            return False
        else:
            raise


# duple: (overwrite, clear_matches, dir, token, concurrency, repos)
def _check_config(config) -> tuple[bool, bool, str, str, int, list] | None:
    if type(config) is not dict:
        logger.error("Config Error: Not a valid config")
        return

    overwrite = config.get("overwrite", True)
    if type(overwrite) is not bool:
        logger.error(
            f'Config Error: "overwrite" must be a boolean, current value: "{overwrite}"'
        )
        return

    clear_matches = config.get("clear_matches", False)
    if type(clear_matches) is not bool:
        logger.error(
            f'Config Error: "clear_matches" must be a boolean, current value: "{clear_matches}"'
        )
        return

    download_dir = config.get("dir", "")
    if type(download_dir) is not str:
        logger.error(
            f'Config Error: "dir" must be a string, current value: "{download_dir}"'
        )
        return

    token = config.get("token", "")
    if type(token) is not str:
        logger.error(
            f'Config Error: "token" must be a string, current value: "{token}"'
        )
        return

    concurrent_num = config.get("concurrency", _DEFAULT_CONCURRENCY)
    if type(concurrent_num) is not int or concurrent_num < 0:
        logger.error(
            f'Config Error: "concurrency" must be an integer greater than or equal to 0, current value: "{concurrent_num}"'
        )
        return

    repos = []
    try:
        repos = config["repos"]
        if type(repos) is not list:
            logger.error(
                f'Config Error: "repos" must be a list, current value: "{repos}"'
            )
            return
    except KeyError:
        logger.error('Config Error: "repos" is required')
        return

    return (overwrite, clear_matches, download_dir, token, concurrent_num, repos)


# duple: (owner, repo, token, patterns)
def _check_repo_config(repo_config) -> tuple[str, str, str, list[re.Pattern]] | None:
    if type(repo_config) is not dict:
        logger.error(
            f'Config Error: Not a valid repo config, current value: "{repo_config}"'
        )
        return

    owner = ""
    try:
        owner = repo_config["owner"]
        if type(owner) is not str or not owner:
            logger.error(
                f'Config Error: "owner" must be a non-empty string, current value: "{owner}"'
            )
            return
    except KeyError:
        logger.error('Config Error: "owner" is required in a repo config')
        return

    repo = ""
    try:
        repo = repo_config["repo"]
        if type(repo) is not str or not repo:
            logger.error(
                f'Config Error: "repo" must be a non-empty string, current value: "{repo}"'
            )
            return
    except KeyError:
        logger.error('Config Error: "repo" is required in a repo config')
        return

    token = repo_config.get("token", "")
    if type(token) is not str:
        logger.error(
            f'Config Error: "token" must be a string, current value: "{token}"'
        )
        return

    filters = repo_config.get("filters", [])
    if type(filters) is not list:
        logger.error(
            f'Config Error: "filters" must be a list, current value: "{filters}"'
        )
        return
    patterns = []
    for filter_item in filters:
        if type(filter_item) is not str:
            logger.error(
                f'Config Error: "filter" must be a string, current value: "{filter_item}"'
            )
            return
        try:
            patterns.append(re.compile(filter_item))
        except re.error as e:
            logger.error(
                f'Config Error: "{filter_item}" is not a valid regular expression: {e}'
            )
            return

    return (owner, repo, token, patterns)


def _clear_matches(dir: str, patterns: list[re.Pattern]) -> bool:
    try:
        success = True
        dir_path = pathlib.Path(dir)
        for file_path in dir_path.iterdir():
            try:
                for pattern_item in patterns:
                    if pattern_item.fullmatch(file_path.name):
                        if file_path.is_file():
                            logger.info(
                                f'Clear Matches: Deleting file "{file_path.name}"'
                            )
                            file_path.unlink()
                        else:
                            success = False
                            logger.warning(
                                f'Clear Matches: "{file_path.name}" is not a regular file'
                            )
                        break
            except OSError as e:
                success = False
                logger.warning(
                    f'Clear Matches: OSError of file "{file_path.name}": {e.strerror if e.strerror else e}'
                )
        return success
    except OSError as e:
        logger.error(
            f'Clear Matches: OSError of directory "{dir_path}": {e.strerror if e.strerror else e}'
        )
        return False


def _parse_release(
    release_info: dict,
    token: str,
    patterns: list[re.Pattern],
    overwrite: bool,
    download_dir: str,
    download_list: list[tuple[str, str, str]],
) -> bool:
    assets = release_info["assets"]
    if not assets:
        return True

    success = True
    for asset_item in assets:
        matched = False
        filename: str = asset_item["name"]
        download_url: str = asset_item["browser_download_url"]

        if not patterns:
            matched = True
        else:
            for pattern_item in patterns:
                if pattern_item.fullmatch(filename):
                    matched = True
                    break
        if matched:
            try:
                file_path = pathlib.Path(download_dir) / filename
                if file_path.exists():
                    logger.info(f'File Exists: "{filename}"')
                    if not overwrite:
                        logger.info(f'Skiped File: "{filename}"')
                    elif not file_path.is_file():
                        success = False
                        logger.warning(
                            f'Overwrite: "{filename}" exists and is not a regular file'
                        )
                    else:
                        logger.info(f'Overwrite File: "{filename}"')
                        download_list.append((download_url, filename, token))
                else:
                    download_list.append((download_url, filename, token))
            except OSError as e:
                success = False
                logger.warning(
                    f'OSError of file "{filename}": {e.strerror if e.strerror else e}'
                )
        else:
            logger.debug(f'Filtered Out: "{filename}"')
    return success


def ghdl(config, log_level=_DEFAULT_LOG_LEVEL) -> bool:
    logger.setLevel(log_level)

    check_result = _check_config(config)
    if not check_result:
        return False
    (
        overwrite,
        clear_matches,
        download_dir,
        global_token,
        concurrent_num,
        repos,
    ) = check_result

    if not repos:
        return True

    try:
        pathlib.Path(download_dir).mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(
            f"Failed to create download directory: {e.strerror if e.strerror else e}"
        )
        return False

    success = True

    # tuple: (url, filename, token)
    download_list: list[tuple[str, str, str]] = []

    if concurrent_num:
        interrupt = threading.Event()
        executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(repos))

        # tuple: (token, patterns)
        release_task_dict: dict[
            concurrent.futures.Future, tuple[str, list[re.Pattern]]
        ] = {}
        try:
            for repo_item in repos:
                check_result = _check_repo_config(repo_item)
                if not check_result:
                    success = False
                    continue
                owner, repo, token, patterns = check_result
                token = token if token else global_token

                if clear_matches:
                    success = _clear_matches(download_dir, patterns) and success

                task = executor.submit(
                    _get_latest_release, owner, repo, token, interrupt
                )
                release_task_dict[task] = (token, patterns)

            for task in concurrent.futures.as_completed(release_task_dict.keys()):
                release_info = task.result()
                if not release_info:
                    success = False
                    continue
                token, patterns = release_task_dict[task]
                success = (
                    _parse_release(
                        release_info,
                        token,
                        patterns,
                        overwrite,
                        download_dir,
                        download_list,
                    )
                    and success
                )
        finally:
            executor.shutdown(wait=True, cancel_futures=True)

        executor = concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_num)
        try:
            asset_task_list = [
                executor.submit(
                    _download_asset, url, filename, download_dir, token, interrupt
                )
                for url, filename, token in download_list
            ]

            for task in concurrent.futures.as_completed(asset_task_list):
                success = task.result() and success
        except KeyboardInterrupt:
            interrupt.set()
            raise
        finally:
            executor.shutdown(wait=True, cancel_futures=True)
    else:
        for repo_item in repos:
            check_result = _check_repo_config(repo_item)
            if not check_result:
                success = False
                continue
            owner, repo, token, patterns = check_result
            token = token if token else global_token

            if clear_matches:
                success = _clear_matches(download_dir, patterns) and success

            release_info = _get_latest_release(owner, repo, token, interrupt=None)
            if not release_info:
                success = False
                continue
            success = (
                _parse_release(
                    release_info,
                    token,
                    patterns,
                    overwrite,
                    download_dir,
                    download_list,
                )
                and success
            )
        for url, filename, token in download_list:
            success = (
                _download_asset(url, filename, download_dir, token, interrupt=None)
                and success
            )

    return success


if __name__ == "__main__":
    log_level_dict = {
        "debug": logging.DEBUG,
        "info": logging.INFO,
        "warning": logging.WARNING,
        "error": logging.ERROR,
        "fatal": logging.FATAL,
    }

    parser = argparse.ArgumentParser(
        prog=_PROG_NAME,
        description="A simple config based python script to download the latest release assets from github.",
    )
    parser.add_argument(
        "-c",
        "--config",
        action="store",
        required=True,
        metavar="PATH",
        dest="config",
        help="path to the config file",
    )
    parser.add_argument(
        "-l",
        "--log-level",
        action="store",
        metavar="LEVEL",
        dest="log_level",
        choices=log_level_dict.keys(),
        help="log level",
    )
    args = parser.parse_args()

    log_level = args.log_level
    log_level = log_level_dict[log_level] if log_level else _DEFAULT_LOG_LEVEL
    logger.setLevel(log_level)

    try:
        with pathlib.Path(args.config).open("r") as config_file:
            config = json.load(config_file)
    except json.JSONDecodeError as e:
        logger.error(f'Config Error: "{args.config}" is not a valid json file: {e}')
        exit(1)
    except OSError as e:
        logger.error(
            f'Config Error: Failed to read the config file "{args.config}": {e.strerror if e.strerror else e}'
        )
        exit(1)

    def signal_handler(signum, frame):
        if signum in [signal.SIGHUP, signal.SIGTERM]:
            raise KeyboardInterrupt

    signal.signal(signal.SIGTERM, signal_handler)
    signal.signal(signal.SIGHUP, signal_handler)

    try:
        exit(0 if ghdl(config, log_level) else 1)
    except KeyboardInterrupt:
        logger.warning("Interrupted by user")
        exit(1)
