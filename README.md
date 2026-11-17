# DuckDB Parquet Notebook

**Created:** 2026-11-17  
**Updated:** 2026-11-17

`parquet_query.ipynb`에서 Parquet 파일의 구조를 확인하고, 지정한 컬럼의 시작값과 종료값으로 구간을 조회합니다. 데이터는 DuckDB로 직접 조회하고, 조회 결과만 pandas DataFrame으로 가져옵니다.

## 실행

터미널에서 다음 명령을 실행합니다. Python 3.12 이상과 uv가 필요합니다.

```bash
cd DuckDB_notebook
uv sync
```

`uv sync`는 저장소의 `.venv`에 의존성을 설치합니다. VS Code Remote - WSL에서 Python 및 Jupyter 확장을 활성화하고, `parquet_query.ipynb`를 연 뒤 **Select Kernel → Python Environments → .venv/bin/python**을 선택합니다. 셀을 위에서부터 실행합니다.

브라우저에서 사용하려면 다음 명령으로 JupyterLab을 실행할 수도 있습니다.

```bash
uv run --with jupyterlab jupyter lab parquet_query.ipynb
```

## 조회 설정

1. 파일 설정의 `PARQUET_PATH`에 파일 경로 또는 `samples/*.parquet` 같은 패턴을 입력합니다. 상대 경로는 저장소 루트를 기준으로 해석합니다.
2. 샘플 파일은 `feature_id`별로 중첩 시계열을 저장합니다. `SERIES_COLUMN`을 `series_1m`, `series_5m`, `series_30m` 중 하나로 지정하면 해당 목록을 펼칩니다. 일반적인 표 형태의 Parquet 파일에서는 `None`으로 설정합니다.
3. 스키마와 최솟값/최댓값을 확인한 뒤 `RANGE_COLUMN`, `START`, `END`를 수정합니다. 기본값은 샘플의 `window_start_us` 숫자 구간입니다. 시간 단위나 기준 시점을 추정해 변환하지 않습니다.
4. `FEATURE_IDS`로 특정 feature를 선택하고, `SELECT_COLUMNS`와 `LIMIT`으로 결과 컬럼과 최대 행 수를 정합니다. 필터를 변경하면 해당 설정 셀과 그 아래 셀을 다시 실행합니다.

구간은 **시작 포함, 종료 제외**(`START <= 값 < END`)입니다. `None`인 경계에는 제한이 없습니다. `START`, `END`가 모두 `None`이면 전체 범위 중 최대 `LIMIT`행을 반환합니다. 구간 컬럼의 NULL 값은 제외합니다. 숫자 컬럼은 숫자로, DATE/TIMESTAMP 컬럼은 ISO 날짜/시간 문자열로 입력합니다. 날짜 문자열의 종료일도 제외되므로 하루 전체를 조회하려면 다음 날 00:00을 종료값으로 입력합니다. TIMESTAMPTZ의 시간대 없는 입력은 `TIMEZONE` 설정을 따릅니다.

샘플의 구간 조회는 각 시계열 항목의 **시작값**을 기준으로 합니다. 항목의 시작과 끝이 조회 구간에 걸쳐 있는지를 검사하는 겹침 조회는 아닙니다. 동일한 구간값을 가진 여러 행이 `LIMIT` 경계에 걸리면 일부만 표시될 수 있습니다. 상세 조회에서 `ORDER_COLUMNS`에 추가 정렬 컬럼을 지정할 수 있습니다.

마지막 셀에서 `EXPORT_CSV = True`로 바꾸면 **현재 표시된 결과**를 `exports/query_result.csv`에 저장합니다. 이 폴더는 Git에서 제외됩니다. 기존 파일이 있으면 덮어쓰지 않으므로 경로를 바꾸거나 기존 파일을 직접 정리하세요.

여러 파일을 읽을 때는 `union_by_name=True`로 컬럼 이름을 맞춥니다. 파일별로 호환되지 않는 타입이나 다른 중첩 구조가 있으면 DuckDB 오류가 발생할 수 있습니다. 큰 중첩 목록은 펼치는 작업 자체에 메모리가 필요하며, `LIMIT`이 원본 스캔이나 정렬 비용까지 제한하지는 않습니다.

## 패키지 관리

런타임 의존성은 `duckdb`, `pandas`이며, 개발 의존성은 노트북 커널과 실행 검증용 `ipykernel`, `nbclient`, `nbformat`입니다. 패키지를 추가할 때는 `uv add 패키지명`을 사용합니다. `uv sync`가 생성하는 `uv.lock`을 함께 커밋하면 동일한 버전을 공유할 수 있습니다.

참고: [uv의 Jupyter 및 VS Code 연동](https://docs.astral.sh/uv/guides/integration/jupyter/), [DuckDB의 Parquet 조회](https://duckdb.org/docs/current/guides/file_formats/query_parquet).
