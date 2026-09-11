"""지원 지역 폴리곤 파일을 담는 패키지.

`__init__.py`를 두는 이유는 setuptools가 `packages.find include=["app*"]`로
찾을 수 있게 하기 위해서다. 그래야 `.geojson`이 이미지에 실린다.
파일 자체는 `data/data/make_region_polygon.py`가 만든다.
"""
