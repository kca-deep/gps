"""
지능형 검색 서비스

한국어 특화 검색 기능을 제공하는 서비스
- 정확한 매칭
- 부분 문자열 매칭  
- 유사도 기반 매칭 (간단한 편집거리)
- 초성 검색
- 별칭/약칭 매칭
"""

import re
import logging
from typing import List, Dict, Any, Tuple, Optional
from dataclasses import dataclass
from datetime import datetime, timedelta

from ..models.wireless_station import WirelessStationDAO, WirelessStation
from ..utils.korean_utils import KoreanUtils
from ..utils.cache_utils import SimpleCache


@dataclass
class SearchResult:
    """검색 결과 데이터 클래스"""
    
    station: WirelessStation
    relevance_score: float  # 연관성 점수 (0-1)
    match_type: str  # 매칭 타입 (exact, partial, fuzzy, chosung)
    distance_meters: Optional[float] = None  # 위치 기반 검색 시 거리


class SmartSearchService:
    """지능형 검색 서비스 클래스"""
    
    def __init__(self):
        """검색 서비스 초기화"""
        self.dao = WirelessStationDAO()
        self.korean_utils = KoreanUtils()
        self.cache = SimpleCache(ttl_seconds=300)  # 5분 캐시
        self.logger = logging.getLogger(__name__)
    
    def search_stations(self, query: str, user_location: Optional[Tuple[float, float]] = None, 
                       page: int = 1, per_page: int = 10) -> Tuple[List[SearchResult], int]:
        """
        통합 무선국 검색
        
        Args:
            query: 검색어
            user_location: 사용자 위치 (lat, lng) - 거리순 정렬용
            page: 페이지 번호
            per_page: 페이지당 결과 수
            
        Returns:
            (검색 결과 리스트, 총 결과 수) 튜플
        """
        try:
            self.logger.info(f"검색 시작: query='{query}', user_location={user_location}, page={page}, per_page={per_page}")
            
            # 빈 검색어 처리
            if not query or not query.strip():
                self.logger.warning("빈 검색어 입력됨")
                return ([], 0)
            
            # 캐시 키 생성
            cache_key = f"search_{query}_{user_location}_{page}_{per_page}"
            cached_result = self.cache.get(cache_key)
            if cached_result:
                self.logger.info("캐시된 검색 결과 반환")
                return cached_result
            
            # 단계별 검색 수행
            all_results = []
            
            # 1. 정확한 매칭
            try:
                exact_results = self._exact_match_search(query)
                all_results.extend([(r, 1.0, "exact") for r in exact_results])
                self.logger.info(f"정확한 매칭: {len(exact_results)}개")
            except Exception as e:
                self.logger.error(f"정확한 매칭 검색 오류: {e}")
            
            # 2. 부분 문자열 매칭
            try:
                partial_results = self._partial_match_search(query)
                # 중복 제거
                existing_ids = {r.station_id for r, _, _ in all_results}
                partial_filtered = [r for r in partial_results if r.station_id not in existing_ids]
                all_results.extend([(r, 0.8, "partial") for r in partial_filtered])
                self.logger.info(f"부분 매칭: {len(partial_filtered)}개")
            except Exception as e:
                self.logger.error(f"부분 매칭 검색 오류: {e}")
            
            # 3. 초성 검색
            try:
                chosung_results = self._chosung_search(query)
                existing_ids.update({r.station_id for r, _, _ in all_results})
                chosung_filtered = [r for r in chosung_results if r.station_id not in existing_ids]
                all_results.extend([(r, 0.6, "chosung") for r in chosung_filtered])
                self.logger.info(f"초성 검색: {len(chosung_filtered)}개")
            except Exception as e:
                self.logger.error(f"초성 검색 오류: {e}")
            
            # 4. 유사도 검색 (간단한 편집거리)
            try:
                fuzzy_results = self._fuzzy_search(query)
                existing_ids.update({r.station_id for r, _, _ in all_results})
                fuzzy_filtered = [r for r in fuzzy_results if r.station_id not in existing_ids]
                all_results.extend([(r, 0.4, "fuzzy") for r in fuzzy_filtered])
                self.logger.info(f"유사도 검색: {len(fuzzy_filtered)}개")
            except Exception as e:
                self.logger.error(f"유사도 검색 오류: {e}")
            
            # SearchResult 객체로 변환
            search_results = []
            for station, score, match_type in all_results:
                try:
                    result = SearchResult(
                        station=station,
                        relevance_score=score,
                        match_type=match_type
                    )
                    
                    # 위치 기반 거리 계산
                    if user_location and station.latitude and station.longitude:
                        from ..models.database import GeoUtils
                        distance = GeoUtils.haversine_distance(
                            user_location[0], user_location[1],
                            station.latitude, station.longitude
                        )
                        result.distance_meters = round(distance * 1000, 1)  # km를 미터로 변환
                    
                    search_results.append(result)
                except Exception as e:
                    self.logger.error(f"검색 결과 변환 오류: {e}")
                    continue
            
            # 정렬 (연관성 점수 우선, 거리 순차)
            if user_location:
                search_results.sort(key=lambda x: (-x.relevance_score, x.distance_meters or float('inf')))
            else:
                search_results.sort(key=lambda x: -x.relevance_score)
            
            # 페이지네이션 적용
            total_count = len(search_results)
            start_idx = (page - 1) * per_page
            end_idx = start_idx + per_page
            paginated_results = search_results[start_idx:end_idx]
            
            # 결과 캐싱
            result = (paginated_results, total_count)
            self.cache.set(cache_key, result)
            
            self.logger.info(f"검색 완료: 총 {total_count}개, 페이지 {len(paginated_results)}개 반환")
            return result
            
        except Exception as e:
            self.logger.error(f"전체 검색 처리 중 오류: {e}")
            return ([], 0)
    
    def _exact_match_search(self, query: str) -> List[WirelessStation]:
        """정확한 매칭 검색"""
        try:
            stations, _ = self.dao.search_stations_by_name(query, page=1, per_page=1000)
            exact_matches = []
            for s in stations:
                if s.station_name == query or (s.station_alias and s.station_alias == query):
                    exact_matches.append(s)
            return exact_matches
        except Exception as e:
            self.logger.error(f"정확한 매칭 검색 중 오류: {e}")
            return []
    
    def _partial_match_search(self, query: str) -> List[WirelessStation]:
        """부분 문자열 매칭 검색"""
        try:
            stations, _ = self.dao.search_stations_by_name(query, page=1, per_page=1000)
            return stations if stations else []
        except Exception as e:
            self.logger.error(f"부분 매칭 검색 중 오류: {e}")
            return []
    
    def _chosung_search(self, query: str) -> List[WirelessStation]:
        """초성 검색"""
        try:
            # 쿼리가 초성인지 확인
            if not self.korean_utils.is_chosung_query(query):
                return []
            
            # 모든 무선국에서 초성 매칭 확인
            all_stations, _ = self.dao.search_stations_by_name("", page=1, per_page=1000)
            
            matching_stations = []
            for station in all_stations:
                try:
                    station_chosung = self.korean_utils.extract_chosung(station.station_name)
                    if query in station_chosung:
                        matching_stations.append(station)
                    
                    # 별칭도 확인
                    if station.station_alias:
                        alias_chosung = self.korean_utils.extract_chosung(station.station_alias)
                        if query in alias_chosung:
                            matching_stations.append(station)
                except Exception as e:
                    self.logger.warning(f"초성 추출 실패 (station_id: {station.station_id}): {e}")
                    continue
            
            return matching_stations
        except Exception as e:
            self.logger.error(f"초성 검색 중 오류: {e}")
            return []
    
    def _fuzzy_search(self, query: str) -> List[WirelessStation]:
        """유사도 기반 검색 (간단한 편집거리)"""
        try:
            all_stations, _ = self.dao.search_stations_by_name("", page=1, per_page=1000)
            
            matching_stations = []
            threshold = max(1, len(query) // 3)  # 쿼리 길이의 1/3까지 허용
            
            for station in all_stations:
                try:
                    # 무선국 이름과 비교
                    distance = self.korean_utils.simple_edit_distance(query, station.station_name)
                    if distance <= threshold:
                        matching_stations.append(station)
                        continue
                    
                    # 별칭과 비교
                    if station.station_alias:
                        distance = self.korean_utils.simple_edit_distance(query, station.station_alias)
                        if distance <= threshold:
                            matching_stations.append(station)
                except Exception as e:
                    self.logger.warning(f"편집거리 계산 실패 (station_id: {station.station_id}): {e}")
                    continue
            
            return matching_stations
        except Exception as e:
            self.logger.error(f"유사도 검색 중 오류: {e}")
            return []
    
    def search_nearby_stations(self, latitude: float, longitude: float, 
                              radius_meters: int = 100) -> List[Dict[str, Any]]:
        """
        근처 무선국 검색
        
        Args:
            latitude: 위도
            longitude: 경도
            radius_meters: 검색 반지름 (미터)
            
        Returns:
            거리 정보가 포함된 무선국 리스트
        """
        cache_key = f"nearby_{latitude}_{longitude}_{radius_meters}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        nearby_stations = self.dao.find_nearby_stations(latitude, longitude, radius_meters)
        
        # 캐싱 (짧은 시간)
        self.cache.set(cache_key, nearby_stations, ttl_seconds=60)
        
        return nearby_stations
    
    def check_location_duplicate(self, latitude: float, longitude: float, 
                                radius_meters: int = 100) -> List[Dict[str, Any]]:
        """
        위치 기반 중복 확인
        
        Args:
            latitude: 위도
            longitude: 경도  
            radius_meters: 중복 확인 반지름 (미터)
            
        Returns:
            중복 가능한 무선국 리스트 (거리 정보 포함)
        """
        return self.search_nearby_stations(latitude, longitude, radius_meters)
    
    def search_by_region_and_type(self, region: str = None, station_type: str = None,
                                  page: int = 1, per_page: int = 10) -> Tuple[List[WirelessStation], int]:
        """
        지역 및 타입별 검색
        
        Args:
            region: 지역명
            station_type: 무선국 타입
            page: 페이지 번호
            per_page: 페이지당 결과 수
            
        Returns:
            (무선국 리스트, 총 결과 수) 튜플
        """
        cache_key = f"region_type_{region}_{station_type}_{page}_{per_page}"
        cached_result = self.cache.get(cache_key)
        if cached_result:
            return cached_result
        
        result = self.dao.search_by_region_and_type(region, station_type, page, per_page)
        
        # 캐싱
        self.cache.set(cache_key, result)
        
        return result
    
    def get_search_suggestions(self, query: str, limit: int = 5) -> List[str]:
        """
        검색어 자동완성 제안
        
        Args:
            query: 입력된 쿼리
            limit: 제안 수 제한
            
        Returns:
            제안 검색어 리스트
        """
        if len(query) < 2:
            return []
        
        # 부분 매칭으로 무선국 이름 찾기
        stations, _ = self.dao.search_stations_by_name(query, page=1, per_page=limit * 2)
        
        suggestions = set()
        for station in stations:
            if station.station_name.startswith(query):
                suggestions.add(station.station_name)
            if station.station_alias and station.station_alias.startswith(query):
                suggestions.add(station.station_alias)
            
            if len(suggestions) >= limit:
                break
        
        return list(suggestions)[:limit]
    
    def get_popular_searches(self, limit: int = 10) -> List[str]:
        """
        인기 검색어 조회
        
        Args:
            limit: 반환할 검색어 수
            
        Returns:
            인기 검색어 리스트
        """
        # 최근 7일간의 검색 로그를 분석
        # 실제로는 search_logs 테이블을 활용해야 함
        # 현재는 더미 데이터 반환
        return [
            "부산항", "관제탑", "기지국", "중계소", "송신소",
            "해운대", "광안리", "김해공항", "울산항", "포항"
        ][:limit]
    
    def log_search(self, session_id: str, user_id: str, query: str, 
                   search_type: str, results_count: int, 
                   selected_station_id: str = None) -> None:
        """
        검색 로그 기록
        
        Args:
            session_id: 세션 ID
            user_id: 사용자 ID
            query: 검색어
            search_type: 검색 타입
            results_count: 결과 수
            selected_station_id: 선택된 무선국 ID
        """
        try:
            from ..models.database import get_db_manager
            
            db_manager = get_db_manager()
            query_sql = """
                INSERT INTO search_logs (
                    session_id, user_id, search_query, search_type,
                    results_count, selected_station_id
                ) VALUES (?, ?, ?, ?, ?, ?)
            """
            
            params = (session_id, user_id, query, search_type, results_count, selected_station_id)
            db_manager.execute_update(query_sql, params)
            
        except Exception as e:
            self.logger.error(f"검색 로그 기록 실패: {e}")


# 전역 검색 서비스 인스턴스
search_service = SmartSearchService()


def get_search_service() -> SmartSearchService:
    """검색 서비스 인스턴스 반환"""
    return search_service 