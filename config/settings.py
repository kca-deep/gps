"""
애플리케이션 설정 관리 모듈
환경 변수를 통한 설정 관리와 기본값 정의
"""

import os
from typing import Optional
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class Config:
    """기본 설정 클래스"""
    
    # OpenAI API 설정
    OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "")

    # TMap API 설정
    TMAP_API_KEY: str = os.getenv("TMAP_API_KEY", "")
    
    # 데이터베이스 설정
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///data/gps_inspection.db")
    
    # Flask 설정
    SECRET_KEY: str = os.getenv("SECRET_KEY", "dev-secret-key-change-in-production")
    FLASK_ENV: str = os.getenv("FLASK_ENV", "development")
    DEBUG: bool = os.getenv("FLASK_DEBUG", "True").lower() == "true"
    
    # 로깅 설정
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    LOG_FILE: str = os.getenv("LOG_FILE", "logs/app.log")
    
    # 데이터베이스 설정
    DATABASE_PATH: str = os.getenv("DATABASE_PATH", "data/gps_inspection.db")
    
    # 지리적 검색 설정
    DEFAULT_SEARCH_RADIUS: int = int(float(os.getenv("DEFAULT_SEARCH_RADIUS", "100")))  # 미터
    MAX_SEARCH_RADIUS: int = int(float(os.getenv("MAX_SEARCH_RADIUS", "5000")))  # 미터
    
    # 검색 알고리즘 설정
    LEVENSHTEIN_THRESHOLD: int = int(float(os.getenv("LEVENSHTEIN_THRESHOLD", "2")))
    SEARCH_CACHE_TTL: int = int(float(os.getenv("SEARCH_CACHE_TTL", "300")))  # 초
    SIMILARITY_THRESHOLD: float = float(os.getenv("SIMILARITY_THRESHOLD", "0.7"))
    MAX_SEARCH_RESULTS: int = int(float(os.getenv("MAX_SEARCH_RESULTS", "50")))
    
    # 페이지네이션 설정
    DEFAULT_PAGE_SIZE: int = int(float(os.getenv("DEFAULT_PAGE_SIZE", "10")))
    MAX_PAGE_SIZE: int = int(float(os.getenv("MAX_PAGE_SIZE", "100")))
    
    # CORS 설정
    CORS_ORIGINS: list = ["http://localhost:3000", "http://127.0.0.1:3000"]
    
    @classmethod
    def validate_config(cls) -> bool:
        """설정 검증"""
        if not cls.OPENAI_API_KEY:
            raise ValueError("OPENAI_API_KEY is required")
        
        if not cls.TMAP_API_KEY:
            raise ValueError("TMAP_API_KEY is required for TMap API integration")

        if not cls.SECRET_KEY or cls.SECRET_KEY == "dev-secret-key-change-in-production":
            if cls.FLASK_ENV == "production":
                raise ValueError("SECRET_KEY must be set in production")
        
        return True


class DevelopmentConfig(Config):
    """개발 환경 설정"""
    DEBUG = True
    LOG_LEVEL = "DEBUG"
    DATABASE_PATH = Config.DATABASE_PATH


class ProductionConfig(Config):
    """운영 환경 설정"""
    DEBUG = False
    LOG_LEVEL = "WARNING"
    DATABASE_PATH = Config.DATABASE_PATH


class TestingConfig(Config):
    """테스트 환경 설정"""
    TESTING = True
    DATABASE_URL = "sqlite:///:memory:"
    LOG_LEVEL = "ERROR"
    DATABASE_PATH = ":memory:"


# 환경별 설정 매핑
config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config() -> Config:
    """현재 환경에 맞는 설정 반환"""
    env = os.getenv("FLASK_ENV", "development")
    config_class = config_map.get(env, DevelopmentConfig)
    return config_class()
