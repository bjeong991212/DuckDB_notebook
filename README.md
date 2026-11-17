# DuckDB Parquet Notebook

**Created:** 2026-11-17  
**Updated:** 2026-11-17

`parquet_query.ipynb`는 컬럼명이나 특정 도메인에 의존하지 않는 로컬 Parquet 탐색 노트북입니다. DuckDB가 스키마를 읽고, 필요한 조회 결과만 pandas DataFrame으로 가져옵니다. 중첩 데이터도 원본 구조를 확인한 뒤 선택해서 펼칠 수 있습니다.

## 실행

Python 3.12 이상과 uv가 필요합니다. WSL 터미널에서 저장소로 이동해 실행합니다.

```bash
cd DuckDB_notebook
uv sync --locked
```

VS Code Remote - WSL에서 Python 및 Jupyter 확장을 활성화하고 `parquet_query.ipynb`를 엽니다. **Select Kernel → Python Environments → .venv/bin/python**을 선택한 뒤 위에서부터 실행합니다. 패키지는 기존 저장소의 `.venv`에서 관리합니다.

브라우저에서 실행하려면 다음 명령을 사용합니다.

```bash
uv run --with jupyterlab jupyter lab parquet_query.ipynb
```

## 파일 선택

노트북의 `PARQUET_PATHS`만 바꾸면 기본 탐색을 시작할 수 있습니다. 기본값은 `samples/*.parquet`이며 샘플 데이터는 저장소에서 별도로 준비해야 합니다.

```python
PARQUET_PATHS = "data/example.parquet"
PARQUET_PATHS = "data/**/*.parquet"
PARQUET_PATHS = "data/"  # 하위 폴더의 *.parquet까지 탐색
PARQUET_PATHS = ["data/part-01.parquet", "data/part-02.parquet"]
```

상대 경로는 노트북이 있는 저장소를 기준으로 해석합니다. WSL에서 Windows 파일은 `/mnt/c/...` 경로를 사용합니다. 파일 선택기는 로컬 파일용이며 원격 URL이나 S3 인증 설정은 포함하지 않습니다.

여러 파일은 컬럼 이름으로 합치며 없는 컬럼은 NULL로 채웁니다. 타입이 호환되지 않으면 파일을 따로 선택하거나 스키마를 맞춰야 합니다. `HIVE_PARTITIONING`은 기본 자동 감지이며 `True` 또는 `False`로 지정할 수 있습니다. 같은 파일을 여러 경로로 지정해도 한 번만 읽습니다.

## 탐색 기능

| 단계 | 기능 | 주요 설정 |
| --- | --- | --- |
| 파일 개요 | 파일별 행 수, 행 그룹, 크기 등 메타데이터 | `PARQUET_PATHS` |
| 구조 확인 | 최상위 스키마, STRUCT 내부 필드 경로, 물리 스키마 | `SHOW_PHYSICAL_SCHEMA` |
| 미리보기 | 앞부분의 원본 행 | `PREVIEW_ROWS` |
| 프로파일 | NULL 수와 비율, 근사 고유값 수, 최솟값/최댓값 | `PROFILE_ROWS` |
| 숫자 분석 | 유한값의 평균, 표준편차, 사분위수, NaN/무한대 개수 | `NUMERIC_COLUMNS` |
| 빈도표 | 값별 개수와 비율, NULL 그룹 포함 | `FREQUENCY_COLUMN`, `TOP_N` |
| 조건 조회 | 컬럼 선택, 여러 필터, 정렬, 페이지 이동 | `SELECT_COLUMNS`, `FILTERS`, `ORDER_BY`, `LIMIT`, `OFFSET` |
| 중첩 탐색 | STRUCT, LIST, ARRAY, MAP을 펼치고 부모 컬럼 보존 | `NESTED_FIELD`, `PARENT_COLUMNS` |
| 직접 SQL | 단일 SELECT/WITH 조회와 매개변수 바인딩 | `CUSTOM_SQL`, `SQL_PARAMS` |
| 저장 | 조건 조회, 중첩 탐색, SQL 결과를 CSV/Parquet로 저장 | `EXPORT_FORMAT`, `EXPORT_RESULT` |

프로파일의 기본 범위는 **앞 10,000행**입니다. 무작위 표본이 아니므로 파일의 앞부분에 치우친 통계일 수 있습니다. `PROFILE_ROWS = None`이면 전체를 분석합니다. 조건 조회와 직접 SQL의 `data` 뷰는 이 프로파일 범위와 무관하게 전체 파일을 조회합니다. 빈도표와 숫자 통계는 `profile_data` 뷰를 사용합니다.

중첩 컬럼은 부모 자체의 NULL만 프로파일링하고 고유값/범위 통계는 생략합니다. STRUCT 내부 필드는 `("address", "city")`처럼 경로로 선택할 수 있습니다. `"address.city"`라는 문자열은 점이 들어 있는 실제 최상위 컬럼명을 의미합니다. LIST/ARRAY 안의 요소나 MAP의 key/value는 중첩 탐색 또는 직접 SQL에서 접근합니다.

## 조건 조회 예시

다음은 예시 컬럼명입니다. 실제 파일의 `schema`와 `field_catalog`를 확인해 바꿔 사용합니다.

```python
SELECT_COLUMNS = ["timestamp", "category", "amount"]
FILTERS = [
    ("timestamp", ">=", "2026-01-01"),
    ("timestamp", "<", "2026-02-01"),
    ("category", "in", ["A", "B"]),
    ("amount", ">=", 100),
]
ORDER_BY = [("timestamp", "asc")]
LIMIT = 1_000
OFFSET = 0
```

조건은 AND로 결합합니다. 지원 연산자는 `=`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `not in`, `contains`, `is null`, `is not null`입니다. OR나 복잡한 조건은 직접 SQL을 사용합니다. 값은 바인딩하고 필드 이름은 스키마에 존재하는지 검증한 뒤 인용합니다.

날짜는 실제 컬럼 타입으로 변환해 비교합니다. 위 예시는 시작일 포함, 종료일 제외입니다. `contains`는 대소문자를 구분하는 부분 문자열 검색이며 `%` 등의 와일드카드를 해석하지 않습니다. `is null`과 `is not null` 조건의 값은 `None`으로 지정합니다. 일반 비교와 `not in`은 NULL 행을 제외합니다.

`TIMEZONE`의 기본값은 `UTC`이며 TIMESTAMPTZ 표시와 시간대 없는 입력 해석에 사용합니다. 숫자로 저장된 시간은 epoch 단위나 기준 시점을 추정하지 않습니다. 정렬이 없으면 행 순서를 보장하지 않으며 페이지 이동을 재현하려면 고유 키까지 정렬 기준에 넣으세요.

## 중첩 탐색과 저장

`NESTED_FIELD`의 기본값은 `None`입니다. `nested_fields`에서 경로를 골라 지정하면 STRUCT를 컬럼으로, LIST/ARRAY를 요소별 행으로, MAP을 key/value 행으로 펼칩니다. `PARENT_COLUMNS`로 선택한 원본 컬럼은 `parent.컬럼명`으로 보존됩니다. NULL/빈 목록은 펼친 결과에 행을 만들지 않습니다. 더 깊은 목록을 반복해서 펼치려면 직접 SQL의 `unnest`를 사용하세요.

`EXPORT_FORMAT = "csv"` 또는 `"parquet"`으로 설정하면 `exports/` 아래 저장합니다. `EXPORT_RESULT`에는 `result`, `nested_result`, `sql_result` 중 하나를 지정합니다. 기존 파일은 덮어쓰지 않습니다. 저장되는 범위는 LIMIT/OFFSET을 적용한 조회 결과입니다.

CSV는 DataFrame의 현재 값을 저장하며 중첩 타입이 문자열로 표현됩니다. Parquet는 원래 DuckDB 조회를 다시 실행해 빈 결과, 중첩값, DECIMAL 등 타입을 보존합니다. 실행 사이 원본 파일이 변경되면 결과도 달라질 수 있습니다. 파일이나 설정을 바꾼 뒤에는 관련 조회 셀을 다시 실행하세요.

큰 파일에서는 통계 계산과 정렬이 전체 스캔을 요구할 수 있습니다. `LIMIT`은 반환 행 수만 제한합니다. 하나의 행에 매우 큰 중첩 목록이 있으면 작은 미리보기에서도 메모리가 필요합니다.

## 의존성과 검증

런타임 패키지는 `duckdb`, `pandas`, `pytz`입니다. `pytz`는 현재 DuckDB의 시간대 포함 데이터를 pandas로 변환할 때 필요합니다. 개발 의존성은 `ipykernel`, `nbclient`, `nbformat`이며 버전은 `uv.lock`으로 고정합니다. 패키지 추가는 `uv add 패키지명`을 사용합니다.

```bash
uv run --locked python -m unittest discover -s tests -v
```

테스트는 임시 Parquet 파일을 만들어 빈 파일, 스키마 병합, 숫자/날짜/NULL 필터, 특수문자 컬럼명, 중첩값, 결과 저장을 검증합니다. 노트북 코드 셀을 같은 Python 프로세스에서 순서대로 실행하므로 Jupyter 서버 없이도 검증할 수 있습니다.

참고: [DuckDB Parquet 메타데이터](https://duckdb.org/docs/current/data/parquet/metadata), [DuckDB UNNEST](https://duckdb.org/docs/current/sql/query_syntax/unnest), [uv Jupyter 연동](https://docs.astral.sh/uv/guides/integration/jupyter/).
