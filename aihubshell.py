#!/usr/bin/env python3



import argparse
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path



# aihubshell -mode l | grep "전라도"
# python aihubshell.py \
#     120 \
#     filekeys.txt \
#     --output-dir /data/public/ghlee/AIHUB_2026/



# --------------------------------------------------
# 충청도 방언 데이터에서 사용하려는 filekey
# 필요 없는 것은 지우면 됨
# 충청도 Training 원천데이터만 받고 싶다면: python download_aihub.py \
    # --dataset-key 데이터셋키 \
    # --group train_source \
    # --output-dir ./chungcheong



# python download_aihub.py \
#     --dataset-key 데이터셋키 \
#     --group valid_source \
#     --output-dir ./chungcheong
# python download_aihub.py \
#     --dataset-key 데이터셋키 \
#     --group train_label \
#     --output-dir ./chungcheong
# export AIHUB_API_KEY=
# export PATH=$PATH:/data/public/ghlee/
# python download_aihub.py \
#     --dataset-key 122 \
#     --group all \
#     --output-dir ./AIHUB_2026/chungcheong
# python download_aihub.py \
#     --dataset-key 데이터셋키 \
#     --filekeys 572596 572597 572598 \
#     --output-dir ./chungcheong
# --------------------------------------------------
ERROR_PATTERNS = [
    r"curl:\s*\(56\)",
    r"unexpected eof",
    r"Unexpected EOF",
    r"SSL_read",
    r"Error is not recoverable",
    r"End-of-central-directory signature not found",
    r"CRC error",
]



DEFAULT_RETRY = 5
DEFAULT_RETRY_DELAY = 15

def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def append_log(log_path: Path, text: str):
    with log_path.open("a", encoding="utf-8") as f:
        f.write(text)
        if not text.endswith("\n"):
            f.write("\n")

def load_filekeys(filekeys_path: Path):
    filekeys = []
    with filekeys_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue

            if line.startswith("#"):
                continue

            # 주석 허용:
            # 572596 # chungcheong_1
            line = line.split("#", 1)[0].strip()

            if not line:
                continue

            try:
                filekeys.append(int(line))
            except ValueError:
                raise ValueError(
                    f"Invalid filekey in {filekeys_path}: {line}"
                )
    return filekeys

def load_completed(completed_path: Path):
    if not completed_path.exists():
        return set()

    completed = set()

    with completed_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()

            if not line:
                continue

            # filekey<TAB>filename<TAB>timestamp
            key = line.split("\t")[0]

            if key.isdigit():
                completed.add(int(key))



    return completed

def record_completed(
    completed_path: Path,
    filekey: int,
    filename: str,
):
    with completed_path.open("a", encoding="utf-8") as f:
        f.write(
            f"{filekey}\t{filename}\t{timestamp()}\n"
        )





def record_failed(
    failed_path: Path,
    filekey: int,
    reason: str,
):
    with failed_path.open("a", encoding="utf-8") as f:
        f.write(
            f"{filekey}\t{timestamp()}\t{reason}\n"
        )





def has_error_pattern(output: str):
    for pattern in ERROR_PATTERNS:
        if re.search(pattern, output, re.IGNORECASE):
            return True



    return False





def run_aihubshell(
    dataset_key: str,
    filekey: int,
    api_key: str,
    output_dir: Path,
    log_path: Path,
):
    cmd = [
        "aihubshell",
        "-mode", "d",
        "-datasetkey", str(dataset_key),
        "-filekey", str(filekey),
        "-aihubapikey", api_key,
    ]



    safe_cmd = [
        "aihubshell",
        "-mode", "d",
        "-datasetkey", str(dataset_key),
        "-filekey", str(filekey),
        "-aihubapikey", "********",
    ]



    header = (
        "\n"
        + "=" * 100
        + "\n"
        + f"[{timestamp()}] START filekey={filekey}\n"
        + "COMMAND: "
        + " ".join(safe_cmd)
        + "\n"
    )



    print(header, end="")
    append_log(log_path, header)



    process = subprocess.Popen(
        cmd,
        cwd=str(output_dir),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )



    output_lines = []



    assert process.stdout is not None



    for line in process.stdout:
        print(line, end="")
        append_log(log_path, line)
        output_lines.append(line)



    process.wait()



    output = "".join(output_lines)



    return {
        "returncode": process.returncode,
        "output": output,
        "has_error": has_error_pattern(output),
    }





def find_recent_zip_files(
    output_dir: Path,
    before_files: set,
):
    after_files = set(output_dir.rglob("*.zip"))



    new_files = list(after_files - before_files)



    if new_files:
        return new_files



    # 기존 파일을 덮어썼을 수도 있으므로
    # 최근 수정된 zip도 후보로 둔다.
    zip_files = list(output_dir.rglob("*.zip"))



    zip_files.sort(
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )



    return zip_files[:5]





def test_zip(zip_path: Path, log_path: Path):
    if not zip_path.exists():
        return False, "zip file does not exist"



    if zip_path.stat().st_size == 0:
        return False, "zip file size is 0"



    print(f"\n[ZIP TEST] {zip_path}")



    cmd = [
        "unzip",
        "-t",
        str(zip_path),
    ]



    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )



    append_log(
        log_path,
        f"\n[ZIP TEST] {zip_path}\n{result.stdout}\n",
    )



    if result.returncode == 0:
        return True, "OK"



    return False, result.stdout[-2000:]





def find_part_files(output_dir: Path):
    candidates = []



    patterns = [
        "*.part*",
        "*.zip.part*",
    ]



    for pattern in patterns:
        candidates.extend(output_dir.rglob(pattern))



    return sorted(set(candidates))





def print_disk_usage(path: Path):
    usage = shutil.disk_usage(path)



    def gb(x):
        return x / (1024 ** 3)



    print(
        f"[DISK] total={gb(usage.total):.1f} GB "
        f"used={gb(usage.used):.1f} GB "
        f"free={gb(usage.free):.1f} GB"
    )





def verify_candidate_zips(
    output_dir: Path,
    before_files: set,
    log_path: Path,
):
    candidates = find_recent_zip_files(
        output_dir,
        before_files,
    )



    if not candidates:
        return False, None, "No zip file found"



    for zip_path in candidates:
        ok, reason = test_zip(
            zip_path,
            log_path,
        )



        if ok:
            return True, zip_path, "OK"



    return (
        False,
        None,
        "No valid zip found among candidates",
    )





def download_one(
    dataset_key: str,
    filekey: int,
    api_key: str,
    output_dir: Path,
    log_path: Path,
    max_retry: int,
    retry_delay: int,
):
    for attempt in range(1, max_retry + 1):



        print()
        print(
            f"===== FILEKEY {filekey} "
            f"ATTEMPT {attempt}/{max_retry} ====="
        )



        print_disk_usage(output_dir)



        before_files = set(
            output_dir.rglob("*.zip")
        )



        result = run_aihubshell(
            dataset_key=dataset_key,
            filekey=filekey,
            api_key=api_key,
            output_dir=output_dir,
            log_path=log_path,
        )



        print()
        print(
            f"[RESULT] returncode={result['returncode']} "
            f"log_error={result['has_error']}"
        )



        # 중요한 부분:
        # curl(56)이 있어도 파일 자체는 정상일 수 있으므로
        # 반드시 zip 테스트를 먼저 한다.
        zip_ok, zip_path, zip_reason = \
            verify_candidate_zips(
                output_dir,
                before_files,
                log_path,
            )



        if zip_ok and zip_path is not None:
            print()
            print(
                f"[SUCCESS] filekey={filekey}"
            )
            print(
                f"[VALID ZIP] {zip_path}"
            )



            return True, zip_path



        print()
        print(
            f"[FAILED] filekey={filekey}"
        )
        print(
            f"[ZIP CHECK] {zip_reason}"
        )



        if result["has_error"]:
            print(
                "[INFO] SSL/EOF related error detected."
            )



        part_files = find_part_files(
            output_dir
        )



        if part_files:
            print(
                f"[INFO] Found {len(part_files)} "
                "part files."
            )



            for p in part_files[-10:]:
                try:
                    size_gb = (
                        p.stat().st_size
                        / (1024 ** 3)
                    )



                    print(
                        f"  {p} "
                        f"{size_gb:.3f} GB"
                    )
                except FileNotFoundError:
                    pass



        if attempt < max_retry:
            print(
                f"[RETRY] waiting "
                f"{retry_delay} seconds..."
            )



            time.sleep(retry_delay)



    return False, None





def main():
    parser = argparse.ArgumentParser(
        description=(
            "AI Hub robust downloader "
            "with retry and zip verification"
        )
    )



    parser.add_argument(
        "dataset_key",
        help="AI Hub dataset key",
    )



    parser.add_argument(
        "filekeys_txt",
        help=(
            "Text file containing "
            "one filekey per line"
        ),
    )



    parser.add_argument(
        "--output-dir",
        default="./aihub_download",
        help="Output directory",
    )



    parser.add_argument(
        "--api-key",
        default=None,
        help=(
            "AI Hub API key. "
            "Prefer environment variable "
            "AIHUB_API_KEY."
        ),
    )



    parser.add_argument(
        "--retry",
        type=int,
        default=DEFAULT_RETRY,
        help=f"Max retry count "
             f"(default={DEFAULT_RETRY})",
    )



    parser.add_argument(
        "--retry-delay",
        type=int,
        default=DEFAULT_RETRY_DELAY,
        help=(
            "Retry delay in seconds "
            f"(default={DEFAULT_RETRY_DELAY})"
        ),
    )



    parser.add_argument(
        "--force",
        action="store_true",
        help=(
            "Download even if filekey "
            "exists in completed.txt"
        ),
    )



    args = parser.parse_args()



    if shutil.which("aihubshell") is None:
        print(
            "ERROR: aihubshell command not found."
        )
        sys.exit(1)



    if shutil.which("unzip") is None:
        print(
            "ERROR: unzip command not found."
        )
        print(
            "Install it with:"
        )
        print(
            "sudo apt install unzip"
        )
        sys.exit(1)



    api_key = (
        args.api_key
        or os.environ.get("AIHUB_API_KEY")
    )



    if not api_key:
        print(
            "ERROR: AI Hub API key not found."
        )
        print()
        print(
            "Recommended:"
        )
        print(
            "export AIHUB_API_KEY='YOUR_API_KEY'"
        )
        sys.exit(1)



    filekeys_path = Path(
        args.filekeys_txt
    ).resolve()



    if not filekeys_path.exists():
        print(
            f"ERROR: filekeys file "
            f"not found: {filekeys_path}"
        )
        sys.exit(1)



    output_dir = Path(
        args.output_dir
    ).resolve()



    output_dir.mkdir(
        parents=True,
        exist_ok=True,
    )



    log_path = (
        output_dir / "download.log"
    )



    completed_path = (
        output_dir / "completed.txt"
    )



    failed_path = (
        output_dir / "failed.txt"
    )



    filekeys = load_filekeys(
        filekeys_path
    )



    completed = load_completed(
        completed_path
    )



    print(
        "=" * 80
    )
    print(
        "AI Hub Robust Downloader"
    )
    print(
        "=" * 80
    )



    print(
        f"Dataset key  : "
        f"{args.dataset_key}"
    )



    print(
        f"Filekeys     : "
        f"{len(filekeys)}"
    )



    print(
        f"Output dir   : "
        f"{output_dir}"
    )



    print(
        f"Retry        : "
        f"{args.retry}"
    )



    print(
        f"Retry delay  : "
        f"{args.retry_delay}s"
    )



    print(
        f"Completed    : "
        f"{len(completed)}"
    )



    print_disk_usage(
        output_dir
    )



    success_count = 0
    fail_count = 0
    skip_count = 0



    for index, filekey in enumerate(
        filekeys,
        start=1,
    ):
        print()
        print(
            "#" * 80
        )



        print(
            f"[{index}/{len(filekeys)}] "
            f"filekey={filekey}"
        )



        print(
            "#" * 80
        )



        if (
            filekey in completed
            and not args.force
        ):
            print(
                f"[SKIP] filekey={filekey} "
                "already completed."
            )



            skip_count += 1
            continue



        ok, zip_path = download_one(
            dataset_key=args.dataset_key,
            filekey=filekey,
            api_key=api_key,
            output_dir=output_dir,
            log_path=log_path,
            max_retry=args.retry,
            retry_delay=args.retry_delay,
        )



        if ok and zip_path is not None:
            record_completed(
                completed_path,
                filekey,
                str(zip_path),
            )



            completed.add(filekey)



            success_count += 1



        else:
            record_failed(
                failed_path,
                filekey,
                "maximum retry exceeded",
            )



            fail_count += 1



    print()
    print(
        "=" * 80
    )



    print(
        "FINISHED"
    )



    print(
        "=" * 80
    )



    print(
        f"Success : {success_count}"
    )



    print(
        f"Skipped : {skip_count}"
    )



    print(
        f"Failed  : {fail_count}"
    )



    print(
        f"Log     : {log_path}"
    )



    print(
        f"Done    : {completed_path}"
    )



    print(
        f"Failed  : {failed_path}"
    )



    if fail_count > 0:
        sys.exit(2)





if __name__ == "__main__":
    main()
