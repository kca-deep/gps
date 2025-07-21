"""
GPS 무선국 검사 AI 채팅 시스템

이 패키지는 무선국 검사관을 위한 AI 기반 채팅 시스템을 제공합니다.
주요 기능:
- 위치 기반 중복 확인
- 지능형 검색 시스템 (한국어 특화)
- 카카오톡 스타일 채팅 UI
- 음성/문자 병행 입력
"""

__version__ = "0.1.0"
__author__ = "GPS Inspection Team"

# 주요 컴포넌트 임포트
from .models import *
from .services import *
from .controllers import *
from .utils import * 