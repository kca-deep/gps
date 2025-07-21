"""
데이터베이스 연결 및 스키마 관리 모듈

SQLite를 사용한 무선국 정보 관리 시스템
공간 검색을 위한 기본적인 구현 포함
"""

import sqlite3
import logging
import os
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from contextlib import contextmanager
import math


class DatabaseManager:
    """데이터베이스 연결 및 스키마 관리 클래스"""
    
    def __init__(self, db_path: str = "data/gps_inspection.db"):
        """
        데이터베이스 매니저 초기화
        
        Args:
            db_path: 데이터베이스 파일 경로
        """
        self.db_path = db_path
        self.logger = logging.getLogger(__name__)
        
        # 데이터베이스 디렉토리 생성
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        
        # 초기 스키마 생성
        self._initialize_database()
    
    def _initialize_database(self) -> None:
        """데이터베이스 초기화 및 스키마 생성"""
        try:
            with self.get_connection() as conn:
                self._create_tables(conn)
                self._create_indexes(conn)
                self.logger.info("데이터베이스 초기화 완료")
        except Exception as e:
            self.logger.error(f"데이터베이스 초기화 실패: {e}")
            raise
    
    def _create_tables(self, conn: sqlite3.Connection) -> None:
        """테이블 생성"""
        
        # 채팅 세션 테이블
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat_sessions (
                session_id TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                started_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        """)
        
        # 무선국 테이블 (공간 검색을 위한 위도/경도 분리)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS wireless_stations (
                station_id TEXT PRIMARY KEY,
                station_name TEXT NOT NULL,
                station_alias TEXT,
                station_type TEXT NOT NULL,
                latitude REAL NOT NULL,
                longitude REAL NOT NULL,
                gps_accuracy REAL,
                tmap_address TEXT,
                region_name TEXT,
                detailed_location TEXT,
                registration_status TEXT DEFAULT '진행중',
                inspector_id TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_accessed DATETIME,
                access_count INTEGER DEFAULT 0
            )
        """)
        
        # 검색 로그 테이블
        conn.execute("""
            CREATE TABLE IF NOT EXISTS search_logs (
                log_id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                user_id TEXT NOT NULL,
                search_query TEXT NOT NULL,
                search_type TEXT,
                results_count INTEGER,
                selected_station_id TEXT,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
            )
        """)
        
        # 안전 정보 테이블
        conn.execute("""
            CREATE TABLE IF NOT EXISTS safety_info (
                safety_id INTEGER PRIMARY KEY AUTOINCREMENT,
                station_id TEXT NOT NULL,
                safety_level INTEGER,
                safety_notes TEXT,
                access_route TEXT,
                hazard_info TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (station_id) REFERENCES wireless_stations(station_id)
            )
        """)
        
        conn.commit()
    
    def _create_indexes(self, conn: sqlite3.Connection) -> None:
        """인덱스 생성"""
        
        # 검색 최적화 인덱스
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_station_search ON wireless_stations(station_name, station_alias)",
            "CREATE INDEX IF NOT EXISTS idx_location_search ON wireless_stations(latitude, longitude)",
            "CREATE INDEX IF NOT EXISTS idx_region_search ON wireless_stations(region_name, station_type)",
            "CREATE INDEX IF NOT EXISTS idx_status_search ON wireless_stations(registration_status, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_search_logs_session ON search_logs(session_id, created_at)",
            "CREATE INDEX IF NOT EXISTS idx_search_logs_query ON search_logs(search_query, search_type)"
        ]
        
        for index_sql in indexes:
            conn.execute(index_sql)
        
        conn.commit()
    
    @contextmanager
    def get_connection(self):
        """데이터베이스 연결 컨텍스트 매니저"""
        conn = None
        try:
            conn = sqlite3.connect(self.db_path)
            conn.row_factory = sqlite3.Row  # 딕셔너리 형태로 결과 반환
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            self.logger.error(f"데이터베이스 연결 오류: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def execute_query(self, query: str, params: tuple = ()) -> List[Dict[str, Any]]:
        """쿼리 실행 및 결과 반환"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            return [dict(row) for row in cursor.fetchall()]
    
    def execute_update(self, query: str, params: tuple = ()) -> int:
        """업데이트 쿼리 실행"""
        with self.get_connection() as conn:
            cursor = conn.execute(query, params)
            conn.commit()
            return cursor.rowcount


class GeoUtils:
    """지리적 계산 유틸리티 클래스"""
    
    @staticmethod
    def haversine_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """
        Haversine 공식을 이용한 두 지점 간 거리 계산 (미터 단위)
        
        Args:
            lat1, lon1: 첫 번째 지점의 위도, 경도
            lat2, lon2: 두 번째 지점의 위도, 경도
            
        Returns:
            두 지점 간 거리 (미터)
        """
        # 지구 반지름 (미터)
        R = 6371000
        
        # 라디안 변환
        lat1_rad = math.radians(lat1)
        lat2_rad = math.radians(lat2)
        delta_lat = math.radians(lat2 - lat1)
        delta_lon = math.radians(lon2 - lon1)
        
        # Haversine 공식
        a = (math.sin(delta_lat / 2) ** 2 + 
             math.cos(lat1_rad) * math.cos(lat2_rad) * 
             math.sin(delta_lon / 2) ** 2)
        c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
        
        return R * c
    
    @staticmethod
    def get_bounding_box(lat: float, lon: float, radius_meters: float) -> Tuple[float, float, float, float]:
        """
        중심점과 반지름으로부터 경계 상자 계산
        
        Args:
            lat, lon: 중심점 위도, 경도
            radius_meters: 반지름 (미터)
            
        Returns:
            (min_lat, max_lat, min_lon, max_lon) 튜플
        """
        # 1도당 대략적인 미터 (위도 기준)
        lat_degree_meters = 111000
        lon_degree_meters = 111000 * math.cos(math.radians(lat))
        
        lat_delta = radius_meters / lat_degree_meters
        lon_delta = radius_meters / lon_degree_meters
        
        return (
            lat - lat_delta,  # min_lat
            lat + lat_delta,  # max_lat
            lon - lon_delta,  # min_lon
            lon + lon_delta   # max_lon
        )


# 전역 데이터베이스 매니저 인스턴스
db_manager = DatabaseManager()


def get_db_manager() -> DatabaseManager:
    """데이터베이스 매니저 인스턴스 반환"""
    return db_manager 