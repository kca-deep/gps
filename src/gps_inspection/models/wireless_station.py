"""
무선국 데이터 모델

무선국 정보의 CRUD 연산 및 비즈니스 로직을 담당
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, List, Dict, Any, Tuple
import uuid
import logging

from .database import get_db_manager, GeoUtils


@dataclass
class WirelessStation:
    """무선국 데이터 클래스"""
    
    station_id: str
    station_name: str
    station_type: str
    latitude: float
    longitude: float
    inspector_id: str
    station_alias: Optional[str] = None
    gps_accuracy: Optional[float] = None
    tmap_address: Optional[str] = None
    region_name: Optional[str] = None
    detailed_location: Optional[str] = None
    registration_status: str = "진행중"
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    last_accessed: Optional[datetime] = None
    access_count: int = 0
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WirelessStation':
        """딕셔너리로부터 WirelessStation 인스턴스 생성"""
        return cls(
            station_id=data['station_id'],
            station_name=data['station_name'],
            station_type=data['station_type'],
            latitude=data['latitude'],
            longitude=data['longitude'],
            inspector_id=data['inspector_id'],
            station_alias=data.get('station_alias'),
            gps_accuracy=data.get('gps_accuracy'),
            tmap_address=data.get('tmap_address'),
            region_name=data.get('region_name'),
            detailed_location=data.get('detailed_location'),
            registration_status=data.get('registration_status', '진행중'),
            created_at=datetime.fromisoformat(data['created_at']) if data.get('created_at') else None,
            updated_at=datetime.fromisoformat(data['updated_at']) if data.get('updated_at') else None,
            last_accessed=datetime.fromisoformat(data['last_accessed']) if data.get('last_accessed') else None,
            access_count=data.get('access_count', 0)
        )
    
    def to_dict(self) -> Dict[str, Any]:
        """WirelessStation을 딕셔너리로 변환"""
        return {
            'station_id': self.station_id,
            'station_name': self.station_name,
            'station_type': self.station_type,
            'latitude': self.latitude,
            'longitude': self.longitude,
            'inspector_id': self.inspector_id,
            'station_alias': self.station_alias,
            'gps_accuracy': self.gps_accuracy,
            'tmap_address': self.tmap_address,
            'region_name': self.region_name,
            'detailed_location': self.detailed_location,
            'registration_status': self.registration_status,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'last_accessed': self.last_accessed.isoformat() if self.last_accessed else None,
            'access_count': self.access_count
        }


class WirelessStationDAO:
    """무선국 데이터 접근 객체"""
    
    def __init__(self):
        """DAO 초기화"""
        self.db_manager = get_db_manager()
        self.logger = logging.getLogger(__name__)
    
    def generate_station_id(self) -> str:
        """
        새로운 무선국 ID 생성
        
        Returns:
            WS + 5자리 숫자 형태의 ID (예: WS00123)
        """
        # 기존 ID 중 최대값 찾기
        query = """
            SELECT station_id FROM wireless_stations 
            WHERE station_id LIKE 'WS%'
            ORDER BY CAST(SUBSTR(station_id, 3) AS INTEGER) DESC
            LIMIT 1
        """
        
        results = self.db_manager.execute_query(query)
        
        if results:
            last_id = results[0]['station_id']
            last_number = int(last_id[2:])  # 'WS' 제거 후 숫자 부분
            new_number = last_number + 1
        else:
            new_number = 1
        
        return f"WS{new_number:05d}"
    
    def create_station(self, station: WirelessStation) -> str:
        """
        새로운 무선국 등록
        
        Args:
            station: 등록할 무선국 정보
            
        Returns:
            생성된 무선국 ID
        """
        if not station.station_id:
            station.station_id = self.generate_station_id()
        
        query = """
            INSERT INTO wireless_stations (
                station_id, station_name, station_alias, station_type,
                latitude, longitude, gps_accuracy, tmap_address,
                region_name, detailed_location, registration_status,
                inspector_id, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """
        
        now = datetime.now()
        params = (
            station.station_id,
            station.station_name,
            station.station_alias,
            station.station_type,
            station.latitude,
            station.longitude,
            station.gps_accuracy,
            station.tmap_address,
            station.region_name,
            station.detailed_location,
            station.registration_status,
            station.inspector_id,
            now,
            now
        )
        
        try:
            self.db_manager.execute_update(query, params)
            self.logger.info(f"무선국 등록 완료: {station.station_id}")
            return station.station_id
        except Exception as e:
            self.logger.error(f"무선국 등록 실패: {e}")
            raise
    
    def get_station_by_id(self, station_id: str) -> Optional[WirelessStation]:
        """
        ID로 무선국 조회
        
        Args:
            station_id: 무선국 ID
            
        Returns:
            WirelessStation 객체 또는 None
        """
        query = """
            SELECT * FROM wireless_stations
            WHERE station_id = ?
        """
        
        results = self.db_manager.execute_query(query, (station_id,))
        
        if results:
            # 조회 수 증가 및 마지막 접근 시간 업데이트
            self._update_access_info(station_id)
            return WirelessStation.from_dict(results[0])
        
        return None
    
    def search_stations_by_name(self, query: str, page: int = 1, per_page: int = 10) -> Tuple[List[WirelessStation], int]:
        """
        이름으로 무선국 검색
        
        Args:
            query: 검색어
            page: 페이지 번호 (1부터 시작)
            per_page: 페이지당 결과 수
            
        Returns:
            (무선국 리스트, 총 결과 수) 튜플
        """
        # 총 결과 수 조회
        count_query = """
            SELECT COUNT(*) as total FROM wireless_stations
            WHERE station_name LIKE ? OR station_alias LIKE ?
        """
        search_pattern = f"%{query}%"
        count_result = self.db_manager.execute_query(count_query, (search_pattern, search_pattern))
        total_count = count_result[0]['total']
        
        # 페이지네이션 적용 검색
        search_query = """
            SELECT * FROM wireless_stations
            WHERE station_name LIKE ? OR station_alias LIKE ?
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        offset = (page - 1) * per_page
        results = self.db_manager.execute_query(
            search_query, 
            (search_pattern, search_pattern, per_page, offset)
        )
        
        stations = [WirelessStation.from_dict(row) for row in results]
        return stations, total_count
    
    def find_nearby_stations(self, latitude: float, longitude: float, radius_meters: int = 100) -> List[Dict[str, Any]]:
        """
        근처 무선국 찾기
        
        Args:
            latitude: 중심점 위도
            longitude: 중심점 경도
            radius_meters: 검색 반지름 (미터)
            
        Returns:
            거리 정보가 포함된 무선국 리스트
        """
        # 경계 상자 계산
        min_lat, max_lat, min_lon, max_lon = GeoUtils.get_bounding_box(
            latitude, longitude, radius_meters
        )
        
        query = """
            SELECT * FROM wireless_stations
            WHERE latitude BETWEEN ? AND ?
            AND longitude BETWEEN ? AND ?
        """
        
        results = self.db_manager.execute_query(query, (min_lat, max_lat, min_lon, max_lon))
        
        # 정확한 거리 계산 및 필터링
        nearby_stations = []
        for row in results:
            distance = GeoUtils.haversine_distance(
                latitude, longitude,
                row['latitude'], row['longitude']
            )
            
            if distance <= radius_meters:
                station_dict = dict(row)
                station_dict['distance_meters'] = round(distance, 1)
                nearby_stations.append(station_dict)
        
        # 거리순 정렬
        nearby_stations.sort(key=lambda x: x['distance_meters'])
        
        return nearby_stations
    
    def search_by_region_and_type(self, region: str = None, station_type: str = None, 
                                  page: int = 1, per_page: int = 10) -> Tuple[List[WirelessStation], int]:
        """
        지역 및 타입으로 무선국 검색
        
        Args:
            region: 지역명 (부분 매칭)
            station_type: 무선국 타입 (부분 매칭)
            page: 페이지 번호
            per_page: 페이지당 결과 수
            
        Returns:
            (무선국 리스트, 총 결과 수) 튜플
        """
        where_conditions = []
        params = []
        
        if region:
            where_conditions.append("region_name LIKE ?")
            params.append(f"%{region}%")
        
        if station_type:
            where_conditions.append("station_type LIKE ?")
            params.append(f"%{station_type}%")
        
        where_clause = " AND ".join(where_conditions) if where_conditions else "1=1"
        
        # 총 결과 수 조회
        count_query = f"SELECT COUNT(*) as total FROM wireless_stations WHERE {where_clause}"
        count_result = self.db_manager.execute_query(count_query, tuple(params))
        total_count = count_result[0]['total']
        
        # 검색 쿼리
        search_query = f"""
            SELECT * FROM wireless_stations
            WHERE {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        
        results = self.db_manager.execute_query(search_query, tuple(params))
        stations = [WirelessStation.from_dict(row) for row in results]
        
        return stations, total_count
    
    def update_station(self, station: WirelessStation) -> bool:
        """
        무선국 정보 업데이트
        
        Args:
            station: 업데이트할 무선국 정보
            
        Returns:
            업데이트 성공 여부
        """
        query = """
            UPDATE wireless_stations SET
                station_name = ?, station_alias = ?, station_type = ?,
                latitude = ?, longitude = ?, gps_accuracy = ?,
                tmap_address = ?, region_name = ?, detailed_location = ?,
                registration_status = ?, updated_at = ?
            WHERE station_id = ?
        """
        
        params = (
            station.station_name,
            station.station_alias,
            station.station_type,
            station.latitude,
            station.longitude,
            station.gps_accuracy,
            station.tmap_address,
            station.region_name,
            station.detailed_location,
            station.registration_status,
            datetime.now(),
            station.station_id
        )
        
        try:
            affected_rows = self.db_manager.execute_update(query, params)
            success = affected_rows > 0
            if success:
                self.logger.info(f"무선국 업데이트 완료: {station.station_id}")
            return success
        except Exception as e:
            self.logger.error(f"무선국 업데이트 실패: {e}")
            return False
    
    def delete_station(self, station_id: str) -> bool:
        """
        무선국 삭제
        
        Args:
            station_id: 삭제할 무선국 ID
            
        Returns:
            삭제 성공 여부
        """
        query = "DELETE FROM wireless_stations WHERE station_id = ?"
        
        try:
            affected_rows = self.db_manager.execute_update(query, (station_id,))
            success = affected_rows > 0
            if success:
                self.logger.info(f"무선국 삭제 완료: {station_id}")
            return success
        except Exception as e:
            self.logger.error(f"무선국 삭제 실패: {e}")
            return False
    
    def _update_access_info(self, station_id: str) -> None:
        """조회 정보 업데이트 (내부 메서드)"""
        query = """
            UPDATE wireless_stations SET
                last_accessed = ?,
                access_count = access_count + 1
            WHERE station_id = ?
        """
        
        try:
            self.db_manager.execute_update(query, (datetime.now(), station_id))
        except Exception as e:
            self.logger.warning(f"조회 정보 업데이트 실패: {e}")
    
    def get_stations_by_status(self, status: str, page: int = 1, per_page: int = 10) -> Tuple[List[WirelessStation], int]:
        """
        상태별 무선국 조회
        
        Args:
            status: 등록 상태 ('진행중', '완료', '검토중' 등)
            page: 페이지 번호
            per_page: 페이지당 결과 수
            
        Returns:
            (무선국 리스트, 총 결과 수) 튜플
        """
        # 'all' 상태일 경우 모든 무선국 조회
        if status == "all":
            where_clause = ""
            params = []
        else:
            where_clause = "WHERE registration_status = ?"
            params = [status]

        # 총 결과 수 조회
        count_query = f"SELECT COUNT(*) as total FROM wireless_stations {where_clause}"
        count_result = self.db_manager.execute_query(count_query, tuple(params))
        total_count = count_result[0]['total']
        
        # 검색 쿼리
        search_query = f"""
            SELECT * FROM wireless_stations
            {where_clause}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        
        offset = (page - 1) * per_page
        params.extend([per_page, offset])
        
        results = self.db_manager.execute_query(search_query, tuple(params))
        stations = [WirelessStation.from_dict(row) for row in results]
        
        return stations, total_count
