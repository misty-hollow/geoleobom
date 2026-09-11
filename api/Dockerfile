# 걸어봄 API 이미지.
#
# 기준: v2.3 4-1(스택·버전 고정), 5절(서버 구성·로그).
#
# - base 이미지는 태그 + digest로 고정한다. latest 금지.
# - GeoPandas 계열(PC 전용)은 들어가지 않는다. v2.3 1-2가 "서버는 표준 sqlite3로
#   R*Tree와 좌표 컬럼만 읽는다"고 정했고, api/pyproject.toml이 그 경계를 지킨다.
# - 데이터 배포본(GeoPackage·OSRM)은 이미지에 넣지 않는다. 5절의 버전 디렉터리를
#   읽기 전용으로 마운트한다. 이미지와 데이터는 따로 교체한다.
# - uvicorn 기본 접근 로그는 끈다(--no-access-log). 그 로그는 쿼리 문자열이 든
#   원본 요청 줄을 남겨 5절의 "좌표 원문·쿼리 문자열 제외"를 어긴다. 대신
#   app/request_log.py의 미들웨어가 허용된 항목만 쓴다.
# - 워커 1(5절). 분석 동시 실행 제한은 앱이 담당한다.

FROM python:3.12.11-slim-bookworm@sha256:519591d6871b7bc437060736b9f7456b8731f1499a57e22e6c285135ae657bf7

# 서버 기본 파이썬(Ubuntu 24.04)과 개발 PC 고정 버전이 모두 3.12다(PROJECT.md 3절).

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /srv/app

# 의존성 먼저 설치해 레이어를 재사용한다. 소스가 바뀌어도 이 레이어는 그대로다.
COPY pyproject.toml ./
COPY app ./app
RUN python -m pip install --no-cache-dir .

# 루트로 돌리지 않는다. 데이터는 읽기 전용 마운트라 쓰기 권한이 필요 없다.
RUN useradd --system --create-home --uid 10001 geoleobom
USER 10001

EXPOSE 8000

# 포트는 컨테이너 내부에만 노출한다. compose에 ports 매핑을 두지 않는다(5절).
CMD ["python", "-m", "uvicorn", "app.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--workers", "1", "--no-access-log"]
