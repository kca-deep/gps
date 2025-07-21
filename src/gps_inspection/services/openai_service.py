import os
import logging
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
from datetime import datetime
import json

try:
    from openai import OpenAI
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False
    logging.warning("OpenAI 라이브러리가 설치되지 않았습니다. 모의 응답을 사용합니다.")

from ..models.wireless_station import WirelessStation
from ..utils.cache_utils import SimpleCache

logger = logging.getLogger(__name__)

@dataclass
class ChatContext:
    """채팅 컨텍스트 정보"""
    session_id: str
    user_location: Optional[Dict[str, float]] = None
    last_action: Optional[str] = None
    search_results: Optional[List[WirelessStation]] = None
    conversation_history: List[Dict[str, str]] = None
    # 무선국 등록 상태 추가
    registration_state: Optional[str] = None  # 'started', 'location_confirmed', 'info_collecting', 'completed'
    registration_data: Optional[Dict[str, Any]] = None
    expecting_search_query: bool = False # 검색어 입력 대기 상태 추가

    def __post_init__(self):
        if self.conversation_history is None:
            self.conversation_history = []
        if self.registration_data is None:
            self.registration_data = {}

class OpenAIService:
    """OpenAI API를 사용한 GPS 무선국 검사 특화 대화 서비스"""
    
    def __init__(self, api_key: Optional[str] = None):
        """
        OpenAI 서비스 초기화
        
        Args:
            api_key: OpenAI API 키 (None일 경우 환경변수에서 로드)
        """
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        self.openai_model = os.getenv('OPENAI_API_MODEL', 'gpt-3.5-turbo') # 기본값 설정
        self._search_service = None
        self._location_service = None
        self.cache = SimpleCache(ttl_seconds=300)  # 5분 캐시
        
        # OpenAI 클라이언트 초기화
        try:
            if (OPENAI_AVAILABLE and 
                self.api_key and 
                self.api_key.strip() and 
                self.api_key != 'your_openai_api_key_here'):
                # OpenAI 클라이언트 초기화 (proxies 인수는 제거)
                self.openai_client = OpenAI(api_key=self.api_key)
                # 연결 테스트 (간단한 completion 호출로 API 키 유효성만 확인)
                try:
                    self.openai_client.chat.completions.create(
                        model=self.openai_model,
                        messages=[{"role": "user", "content": "hello"}],
                        max_tokens=5
                    )
                    self.client_available = True
                    logger.info(f"OpenAI 클라이언트 초기화 및 모델 '{self.openai_model}' 연결 확인 완료")
                except Exception as api_test_e:
                    logger.warning(f"OpenAI API 테스트 호출 실패: {api_test_e}")
                    self.client_available = False
            else:
                raise Exception("API 키가 설정되지 않음 또는 유효하지 않음")
        except Exception as e:
            self.openai_client = None
            self.client_available = False
            logger.warning(f"OpenAI 클라이언트 초기화 실패: {e}")
            logger.info("로컬 Function Calling 모드로 실행합니다.")
    
    @property
    def search_service(self):
        """SearchService lazy loading"""
        if self._search_service is None:
            from ..services.search_service import SmartSearchService
            self._search_service = SmartSearchService()
        return self._search_service
    
    @property
    def location_service(self):
        """LocationService lazy loading"""
        if self._location_service is None:
            from ..services.location_service import LocationService
            self._location_service = LocationService()
        return self._location_service
    
    def get_system_prompt(self) -> str:
        """GPS 무선국 검사 특화 시스템 프롬프트"""
        return """당신은 GPS 무선국 검사 전문 AI 어시스턴트입니다.

역할과 목적:
- GPS 무선국 등록, 검사, 관리에 대한 전문 지원
- 한국의 무선국 법규 및 기술 기준 안내
- 위치 기반 무선국 검색 및 중복 확인
- 효율적인 검사 업무 지원

주요 기능:
1. 무선국 등록 및 검사 절차 안내
2. 위치 기반 무선국 검색 (GPS 좌표 활용)
3. 기존 무선국과의 중복 여부 확인
4. 무선국 기술 기준 및 법규 정보 제공
5. 검사 일정 및 절차 관리

무선국 등록 프로세스:
- 사용자가 "무선국 등록", "새 무선국 추가" 등을 요청할 때
- GPS 좌표가 없는 경우에만 getCurrentGPS() 함수로 현재 위치 획득
- 기존 GPS 좌표가 있으면 바로 getAddressFromTmap() 함수로 주소 변환
- 필요한 정보 수집 (무선국명, 종류, 담당자 등)
- saveRadioStation() 함수로 데이터베이스 저장
- updateRegistrationState() 함수로 진행 상태 관리

Function Calling 사용 가이드라인:
- GPS 좌표가 없는 경우에만 getCurrentGPS() 호출
- GPS 좌표 확보 후 getAddressFromTmap()로 주소 확인
- 사용자에게 위치 확인 및 추가 정보 요청
- 모든 정보 수집 완료 후 saveRadioStation() 호출
- 각 단계마다 updateRegistrationState()로 상태 업데이트

응답 가이드라인:
- 정확하고 전문적인 정보 제공
- 한국어로 친근하고 이해하기 쉽게 설명
- 구체적인 GPS 좌표나 기술 사양 요청 시 정확한 데이터 활용
- 법규나 기준에 대해서는 최신 정보 기반으로 안내
- 안전 및 규정 준수 강조
- 등록 과정에서는 단계별 안내 및 확인 절차 진행

톤 앤 매너:
- 전문적이지만 친근한 말투
- 복잡한 기술 내용도 쉽게 설명
- 사용자의 업무 효율성을 높이는 실용적 조언
- 필요시 단계별 가이드 제공
- 등록 과정에서는 명확하고 안내적인 톤 사용"""

    def process_message(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """
        사용자 메시지 처리 및 응답 생성
        
        Args:
            message: 사용자 메시지
            context: 채팅 컨텍스트
            
        Returns:
            응답 딕셔너리 (response, actions, data 포함)
        """
        try:
            # 캐시 비활성화 (디버깅용)
            # cache_key = f"chat_{context.session_id}_{hash(message)}_{context.expecting_search_query}_{context.registration_state}"
            # cached_response = self.cache.get(cache_key)
            # if cached_response:
            #     logger.debug("캐시된 응답 반환")
            #     return cached_response
            
            logger.info(f"메시지 처리 시작: message='{message}', expecting_search_query={context.expecting_search_query}")
            
            # 메시지 분석 및 액션 결정
            action_result = self._analyze_message(message, context)
            
            if action_result['action'] != 'chat':
                # 특정 액션 처리 (검색, 등록 등)
                response = self._handle_action(action_result, context)
            else:
                # 일반 대화 처리
                response = self._generate_chat_response(message, context)
            
            # 캐시에 저장 (비활성화)
            # self.cache.set(cache_key, response)
            
            # 대화 히스토리 업데이트
            context.conversation_history.append({
                "user": message,
                "assistant": response['response'],
                "timestamp": datetime.now().isoformat()
            })
            
            return response
            
        except Exception as e:
            logger.error(f"메시지 처리 중 오류: {e}")
            return {
                "response": "죄송합니다. 일시적인 오류가 발생했습니다. 다시 시도해 주세요.",
                "actions": ["retry"],
                "data": None,
                "error": str(e)
            }
    
    def _analyze_message(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """메시지 분석 및 액션 결정"""
        message_lower = message.lower().strip()
        
        # 빠른 액션 메시지 매핑
        action_message_map = {
            "무선국 등록해줘": "register",
            "gps 정보 다시 확인": "reconfirm_gps", # 새로운 액션 추가
            "내 위치 주변 무선국 검색": "nearby",
            "무선국 검색해줘": "search",
            "무선국 목록 보여줘": "list",
            "주소로 좌표 찾기": "address_search", # 주소 검색 액션 추가
            "수동 좌표 입력": "manual_location_input", # 수동 좌표 입력 액션 추가
            "request_location": "request_location_permission" # 위치 권한 요청 액션 추가
        }

        # 정확한 액션 메시지 매칭
        if message_lower in action_message_map:
            return {'action': action_message_map[message_lower], 'message': message}

        # 검색어 입력 대기 상태인 경우 (최우선 처리)
        if context.expecting_search_query:
            context.expecting_search_query = False # 상태 초기화
            logger.info(f"검색어 입력 처리: '{message}'")
            return {'action': 'search', 'message': message} # 현재 메시지를 검색어로 사용

        # 등록 진행 중인지 확인 (우선순위 최고)
        if hasattr(context, 'registration_state') and context.registration_state == "address_confirmed":
            # 등록 정보 입력 단계 - 메시지를 무선국 정보로 파싱
            # 이 부분은 _handle_registration_info_action에서 OpenAI API를 통해 파싱하도록 변경될 예정
            parsed_info = self._parse_registration_info(message) # 임시로 기존 로직 유지
            return {'action': 'registration_info', 'message': message, 'parsed_info': parsed_info}
        
        # 주소 검색 패턴 확인
        if message.startswith('주소로 좌표 찾기:'):
            address = message.replace('주소로 좌표 찾기:', '').strip()
            return {'action': 'address_search', 'message': message, 'address': address}
        
        # 키워드 기반 액션 분석 (기존 로직 유지)
        registration_keywords = ['등록', '신규', '새로운', '추가', '생성', '입력', '저장', '무선국등록', '무선국추가', '새무선국']
        search_keywords = ['검색', '찾기', '조회', '탐색', '찾아줘', '검색해줘']
        nearby_keywords = ['근처', '주변', '거리', '가까운', '인근', '반경']
        list_keywords = ['목록', '리스트', '전체', '모든', '모두', '리스팅']
        help_keywords = ['도움말', '사용법', '가이드', '도움', '설명', '방법']
        address_keywords = ['주소', '주소로', '주소검색', '주소찾기']
        
        if any(keyword in message_lower for keyword in registration_keywords):
            return {'action': 'register', 'message': message}
        elif any(keyword in message_lower for keyword in address_keywords) and any(keyword in message_lower for keyword in ['좌표', '찾기', '검색']):
            return {'action': 'address_search', 'message': message, 'address': message}
        elif any(keyword in message_lower for keyword in search_keywords):
            logger.info(f"검색 키워드 감지: message='{message}'")
            return {'action': 'search', 'message': message}
        elif any(keyword in message_lower for keyword in nearby_keywords):
            return {'action': 'nearby', 'message': message}
        elif any(keyword in message_lower for keyword in list_keywords):
            return {'action': 'list', 'message': message}
        elif any(keyword in message_lower for keyword in help_keywords):
            return {'action': 'help', 'message': message}
        else:
            return {'action': 'chat', 'message': message}

    def _handle_action(self, action_result: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """특정 액션 처리"""
        action = action_result['action']
        message = action_result['message']
        
        if action == 'search':
            return self._handle_search_action(message, context)
        elif action == 'nearby':
            return self._handle_nearby_action(message, context)
        elif action == 'register':
            return self._handle_register_action(message, context)
        elif action == 'registration_info':
            return self._handle_registration_info_action(action_result, context)
        elif action == 'address_search':
            return self._handle_address_search_action(action_result, context)
        elif action == 'list':
            return self._handle_list_action(message, context)
        elif action == 'help':
            return self._handle_help_action(message, context)
        elif action == 'reconfirm_gps':
            return self._handle_reconfirm_gps_action(context) # 새로운 핸들러 호출
        else:
            return self._generate_chat_response(message, context)
    
    def _handle_search_action(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """검색 액션 처리"""
        logger.info(f"검색 액션 처리 시작: message='{message}', expecting_search_query={context.expecting_search_query}")
        
        # '무선국 검색해줘'와 같이 일반적인 검색 요청일 경우 검색어를 다시 요청
        if message.strip() == "무선국 검색해줘":
            context.expecting_search_query = True # 검색어 입력 대기 상태로 설정
            logger.info("검색어 입력 대기 상태로 설정")
            return {
                "response": "어떤 무선국을 검색하시겠습니까? 무선국명, 지역명, 또는 키워드를 입력해 주세요.",
                "actions": ["search_input"],
                "data": None
            }
        
        # 실제 검색어가 들어온 경우 (expecting_search_query가 False이고 구체적인 검색어가 있는 경우)
        search_terms = message.strip()
        
        # 검색어에서 불필요한 단어 제거
        if not context.expecting_search_query:
            search_terms = message.replace('검색', '').replace('찾기', '').replace('조회', '').replace('해줘', '').strip()
        
        if not search_terms: # 여전히 검색어가 비어있다면 다시 요청
            context.expecting_search_query = True # 검색어 입력 대기 상태로 설정
            logger.info("검색어가 비어있어서 다시 요청")
            return {
                "response": "무엇을 검색하시겠습니까? 무선국명, 지역명, 또는 키워드를 입력해 주세요.",
                "actions": ["search_input"],
                "data": None
            }
        
        logger.info(f"검색 실행: search_terms='{search_terms}'")
        
        try:
            # 검색 실행
            # search_stations는 (results, total_count) 튜플을 반환
            user_loc = None
            if context.user_location and 'latitude' in context.user_location and 'longitude' in context.user_location:
                user_loc = (context.user_location['latitude'], context.user_location['longitude'])
            
            search_results_tuple = self.search_service.search_stations(
                query=search_terms,
                user_location=user_loc,
                page=1,
                per_page=10
            )
            
            search_results = search_results_tuple[0] # SearchResult 객체 리스트
            total_count = search_results_tuple[1]
            
            logger.info(f"검색 완료: {len(search_results)}개 결과, 총 {total_count}개")
            
        except Exception as e:
            logger.error(f"검색 실행 중 오류: {e}")
            return {
                "response": f"검색 중 오류가 발생했습니다: {str(e)}",
                "actions": ["search_again"],
                "data": None
            }
        
        if search_results:
            response = f"'{search_terms}' 검색 결과 {total_count}개를 찾았습니다:\n\n"
            for i, result_item in enumerate(search_results[:5], 1): # SearchResult 객체
                station = result_item.station # WirelessStation 객체
                response += f"{i}. {station.station_name}\n"
                response += f"   📍 위치: {station.tmap_address or '주소 정보 없음'}\n"
                response += f"   🗺️ GPS: {station.latitude:.6f}, {station.longitude:.6f}\n"
                if context.user_location:
                    # SearchResult에 이미 distance_meters가 계산되어 있음
                    if result_item.distance_meters is not None:
                        response += f"   📏 거리: {result_item.distance_meters / 1000:.2f}km\n" # 미터를 킬로미터로 변환
                response += "\n"
            
            context.search_results = [item.station for item in search_results] # WirelessStation 객체만 저장
            
            return {
                "response": response,
                "actions": ["view_details", "search_again", "nearby_search"],
                "data": {
                    "search_results": [item.station.to_dict() for item in search_results[:5]],
                    "total_count": total_count
                }
            }
        else:
            return {
                "response": f"'{search_terms}'에 대한 검색 결과가 없습니다. 다른 키워드로 검색해 보세요.",
                "actions": ["search_suggestions", "nearby_search"],
                "data": None
            }
    
    def _handle_nearby_action(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """근처 검색 액션 처리"""
        if not context.user_location:
            return {
                "response": "근처 무선국을 검색하려면 현재 위치 정보가 필요합니다. 위치 권한을 허용해 주세요.",
                "actions": ["request_location"],
                "data": None
            }
        
        # 반경 추출 (기본값: 5km)
        import re
        radius_match = re.search(r'(\d+)\s*(?:km|킬로|키로)', message)
        radius = float(radius_match.group(1)) if radius_match else 5.0
        
        nearby_result = self.location_service.get_nearby_stations_detailed(
            latitude=context.user_location['latitude'],
            longitude=context.user_location['longitude'],
            radius_meters=int(radius * 1000) # km를 미터로 변환하여 전달
        )
        nearby_stations = nearby_result.get('all_stations', [])
        logger.info(f"[_handle_nearby_action] nearby_stations: {nearby_stations}") # 로깅 추가
        
        if nearby_stations:
            # 응답 메시지는 일반 텍스트로 제공
            response_text = f"현재 위치에서 반경 {radius}km 내 무선국 {len(nearby_stations)}개를 찾았습니다."
            
            # GeoUtils 임포트
            from ..models.database import GeoUtils
            
            # 프론트엔드에서 사용할 데이터 구성
            stations_for_data = []
            for station in nearby_stations:
                distance = GeoUtils.haversine_distance( # GeoUtils 직접 호출로 변경
                    context.user_location['latitude'],
                    context.user_location['longitude'],
                    station['latitude'],
                    station['longitude']
                )
                stations_for_data.append({
                    "station_id": station.get('station_id'),
                    "station_name": station.get('station_name'),
                    "station_type": station.get('station_type'),
                    "latitude": station.get('latitude'),
                    "longitude": station.get('longitude'),
                    "tmap_address": station.get('tmap_address'),
                    "distance_meters": distance * 1000 # 미터로 저장
                })
            
            return {
                "response": response_text,
                "actions": ["view_details", "change_radius", "register_new"],
                "data": {
                    "nearby_stations": stations_for_data,
                    "total_count": len(nearby_stations),
                    "radius": radius,
                    "display_type": "nearby_stations_table" # 프론트엔드에서 표 형태로 렌더링하도록 지시
                }
            }
        else:
            return {
                "response": f"반경 {radius}km 내에 등록된 무선국이 없습니다. 새로운 무선국을 등록하시겠습니까?",
                "actions": ["register_new", "change_radius"],
                "data": {"radius": radius}
            }
    
    def _handle_register_action(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """등록 액션 처리 - 단계별 워크플로우 구현"""
        
        # 등록 상태에 따른 처리
        if context.registration_state == "started":
            # 이미 등록 진행 중인 경우
            return {
                "response": "무선국 등록이 이미 진행 중입니다. 현재 단계를 완료해 주세요.",
                "data": {"step": "in_progress"}
            }
        elif context.registration_state == "address_confirmed":
            # 정보 입력 단계 - 새로운 등록 진행하지 않고 현재 진행 상황 안내
            return {
                "response": """현재 무선국 등록이 진행 중입니다.

📋 필요한 정보를 계속 입력해 주세요:
- 무선국명 (예: 홍길동 아마추어 무선국)
- 무선국 종류 (예: 아마추어, 간이, 업무용 등)  
- 담당자명
- 연락처

무선국명을 입력해 주세요:""",
                "data": {"step": "info_collection_reminder"}
            }
        elif context.registration_state == "completed":
            # 이전 등록이 완료된 경우
            context.registration_state = None
            context.registration_data = {}
        
        # GPS 좌표가 이미 있는지 확인
        if context.user_location and 'latitude' in context.user_location and 'longitude' in context.user_location:
            # 이미 GPS 좌표가 있는 경우 바로 주소 변환 실행
            latitude = context.user_location['latitude']
            longitude = context.user_location['longitude']
            
            # 주소 변환 실행
            address_result = self._get_address_from_tmap(latitude, longitude)
            
            if address_result["success"]:
                # 주소 변환 성공
                context.registration_state = "address_confirmed"
                context.registration_data = {
                    "step": "info_collection",
                    "latitude": latitude,
                    "longitude": longitude,
                    "address": address_result["address"],
                    "region_name": address_result.get("region_name", "")
                }
                
                return {
                    "response": f"""🚀 무선국 등록을 시작합니다!

📍 현재 위치: {latitude:.6f}, {longitude:.6f}
🏠 주소: {address_result['address']}
📍 지역: {address_result.get('region_name', '알 수 없음')}

위치 확인이 완료되었습니다. 이제 무선국 정보를 입력해 주세요.

📋 필요한 정보:
- 무선국명 (예: 홍길동 아마추어 무선국)
- 무선국 종류 (예: 아마추어, 간이, 업무용 등)
- 담당자명
- 연락처

무선국명을 입력해 주세요:""",
                    "data": {
                        "step": "info_collection",
                        "location": {
                            "latitude": latitude,
                            "longitude": longitude,
                            "address": address_result["address"],
                            "region": address_result.get("region_name", "")
                        }
                    }
                }
            else:
                # 주소 변환 실패
                context.registration_state = "gps_acquired"
                context.registration_data = {
                    "step": "address_failed",
                    "latitude": latitude,
                    "longitude": longitude
                }
                
                return {
                    "response": f"""🚀 무선국 등록을 시작합니다!

📍 현재 위치: {latitude:.6f}, {longitude:.6f}
❌ 주소 변환에 실패했습니다: {address_result.get('error', '알 수 없는 오류')}

좌표 정보로 등록을 계속 진행하시겠습니까?

📋 필요한 정보:
- 무선국명 (예: 홍길동 아마추어 무선국)
- 무선국 종류 (예: 아마추어, 간이, 업무용 등)
- 담당자명
- 연락처

무선국명을 입력해 주세요:""",
                    "data": {
                        "step": "info_collection",
                        "location": {
                            "latitude": latitude,
                            "longitude": longitude,
                            "address": f"좌표: {latitude:.6f}, {longitude:.6f}",
                            "region": "좌표 기반"
                        },
                        "address_failed": True
                    }
                }
        else:
            # GPS 좌표가 없는 경우에만 위치 요청
            context.registration_state = "started"
            context.registration_data = {"step": "location_check"}
            
            # OpenAI 모델이 getCurrentGPS 함수를 호출하도록 유도
            # 이 응답은 모델에게 현재 위치를 획득해야 함을 알립니다.
            return {
                "response": """🚀 새로운 무선국 등록을 시작합니다!

GPS 좌표를 자동으로 획득하고 주소로 변환해 드린 후 등록을 진행하겠습니다.

📍 위치 권한이 필요합니다. 브라우저에서 위치 허용을 눌러주세요.""",
                "actions": ["request_location"], # 클라이언트에게 위치 요청을 트리거
                "data": {"step": "location_check", "auto_get_gps": True, "function_call_suggestion": {"name": "getCurrentGPS"}}
            }
    
    def _handle_list_action(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """목록 조회 액션 처리"""
        from ..models.wireless_station import WirelessStationDAO
        dao = WirelessStationDAO()
        stations, total = dao.get_stations_by_status("all", page=1, per_page=20)
        
        if stations:
            response = f"등록된 무선국 목록 (최근 {len(stations)}개):\n\n"
            for i, station in enumerate(stations, 1):
                response += f"{i}. {station.station_name}\n"
                response += f"   위치: {station.tmap_address or '주소 정보 없음'}\n"
                # created_at이 이미 ISO 형식 문자열이므로 직접 사용
                response += f"   등록일: {station.created_at or 'N/A'}\n\n"
            
            return {
                "response": response,
                "actions": ["search", "register_new", "view_details"],
                "data": {
                    "stations": [station.to_dict() for station in stations],
                    "total_count": len(stations)
                }
            }
        else:
            return {
                "response": "등록된 무선국이 없습니다. 새로운 무선국을 등록하시겠습니까?",
                "actions": ["register_new"],
                "data": None
            }
    
    def _handle_help_action(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """도움말 액션 처리"""
        help_text = """🚀 GPS 무선국 검사 AI 채팅 시스템 사용법

주요 기능:
• **검색**: "○○ 검색" 또는 "○○ 찾기"
• **근처 조회**: "근처 무선국" 또는 "주변 5km"
• **새 등록**: "무선국 등록" 또는 "신규 등록"
• **목록 보기**: "무선국 목록" 또는 "전체 조회"

사용 예시:
• "서울역 근처 무선국 검색"
• "반경 3km 내 기지국 조회"
• "새로운 중계기 등록"
• "KT 무선국 찾기"

💡 팁:
- 위치 권한을 허용하면 더 정확한 결과를 받을 수 있습니다
- 구체적인 키워드를 사용하면 검색 정확도가 높아집니다
- 좌표는 위도, 경도 순서로 입력해 주세요

무엇을 도와드릴까요?"""
        
        return {
            "response": help_text,
            "actions": ["search", "nearby_search", "register_new", "list_stations"],
            "data": None
        }
    
    def _generate_chat_response(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """OpenAI API를 사용한 일반 대화 응답 생성 (또는 로컬 Function Calling)"""
        if not self.client_available:
            # 로컬 Function Calling 처리
            return self._handle_local_function_calling(message, context)
        
        try:
            # 시스템 프롬프트와 대화 히스토리 준비
            messages = [{"role": "system", "content": self.get_system_prompt()}]
            
            # 등록 상태 정보 추가
            if context.registration_state:
                state_info = f"현재 무선국 등록 상태: {context.registration_state}"
                if context.registration_data:
                    state_info += f"\n수집된 정보: {context.registration_data}"
                messages.append({"role": "system", "content": state_info})
            
            # 최근 대화 히스토리 추가 (최대 10개)
            for history in context.conversation_history[-10:]:
                messages.append({"role": "user", "content": history["user"]})
                messages.append({"role": "assistant", "content": history["assistant"]})
            
            # 현재 메시지 추가
            messages.append({"role": "user", "content": message})
            
            # OpenAI API 호출 (Function Calling 포함)
            response = self.openai_client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=messages,
                functions=self.get_function_definitions(),
                function_call="auto",
                max_tokens=500,
                temperature=0.7
            )
            
            response_message = response.choices[0].message
            
            # Function Calling 처리
            if response_message.function_call:
                function_name = response_message.function_call.name
                function_args = json.loads(response_message.function_call.arguments)
                
                # 함수 실행
                function_result = self.execute_function(function_name, function_args, context)
                
                # 함수 결과를 대화에 추가
                messages.append({
                    "role": "assistant",
                    "content": None,
                    "function_call": {
                        "name": function_name,
                        "arguments": response_message.function_call.arguments
                    }
                })
                messages.append({
                    "role": "function",
                    "name": function_name,
                    "content": json.dumps(function_result, ensure_ascii=False)
                })
                
                # 함수 결과를 바탕으로 최종 응답 생성
                final_response = self.openai_client.chat.completions.create(
                    model="gpt-3.5-turbo",
                    messages=messages,
                    max_tokens=500,
                    temperature=0.7
                )
                
                assistant_response = final_response.choices[0].message.content.strip()
                
                # 특별한 액션이 필요한 경우 추가
                actions = ["search", "nearby_search", "register_new", "help"]
                response_data = None
                
                # GPS 요청이 필요한 경우
                if function_result.get("request_gps"):
                    actions.insert(0, "request_location")
                
                # 등록 완료된 경우
                if function_name == "saveRadioStation" and function_result.get("success"):
                    actions = ["view_station", "register_another", "search"]
                    response_data = {
                        "registered_station": function_result.get("station_data"),
                        "station_id": function_result.get("station_id")
                    }
                
                return {
                    "response": assistant_response,
                    "actions": actions,
                    "data": response_data,
                    "function_called": function_name,
                    "function_result": function_result
                }
            else:
                # 일반 응답
                assistant_response = response_message.content.strip()
                
                return {
                    "response": assistant_response,
                    "actions": ["search", "nearby_search", "register_new", "help"],
                    "data": None
                }
            
        except Exception as e:
            logger.error(f"OpenAI API 호출 실패: {e}")
            return self._handle_local_function_calling(message, context)
    
    def _handle_local_function_calling(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """로컬 Function Calling 처리 (OpenAI API 없이)"""
        message_lower = message.lower().strip()
        
        # 등록 관련 키워드 체크
        registration_keywords = ['등록', '신규', '새로운', '추가', '생성', '입력', '저장']
        is_registration_request = any(keyword in message_lower for keyword in registration_keywords)
        
        # 등록 진행 중인 경우 처리
        if hasattr(context, 'registration_state') and context.registration_state:
            if context.registration_state == "address_confirmed":
                # 무선국 정보 입력 단계
                parsed_info = self._parse_registration_info(message)
                if parsed_info:
                    context.registration_data.update(parsed_info)
                    
                    # 필수 정보 확인
                    required_fields = ['station_name', 'station_type', 'contact_person', 'contact_phone']
                    missing_fields = []
                    for field in required_fields:
                        if not context.registration_data.get(field):
                            missing_fields.append(field)
                    
                    if not missing_fields:
                        # 모든 정보가 있으면 등록 실행
                        save_result = self._save_radio_station(context.registration_data, context)
                        if save_result["success"]:
                            context.registration_state = "completed"
                            return {
                                "response": f"""🎉 무선국 등록이 완료되었습니다!

📋 등록된 정보:
• 무선국명: {context.registration_data['station_name']}
• 종류: {context.registration_data['station_type']}
• 위치: {context.registration_data['latitude']:.6f}, {context.registration_data['longitude']:.6f}
• 담당자: {context.registration_data['contact_person']}

등록번호: {save_result.get('station_id')}""",
                                "actions": ["view_station", "register_another", "search"],
                                "data": {
                                    "registered_station": context.registration_data,
                                    "station_id": save_result.get('station_id')
                                }
                            }
                        else:
                            return {
                                "response": f"❌ 등록 실패: {save_result.get('error')}",
                                "actions": ["retry", "help"],
                                "data": None
                            }
                    else:
                        # 추가 정보 필요
                        return {
                            "response": f"""입력해 주신 정보를 확인했습니다.

✅ 현재 정보: {self._format_registration_info(context.registration_data)}

추가로 필요한 정보를 입력해 주세요.""",
                            "actions": [],
                            "data": {"missing_fields": missing_fields}
                        }
                else:
                    return {
                        "response": "무선국 정보를 다시 입력해 주세요. (무선국명, 종류, 담당자)",
                        "actions": [],
                        "data": None
                    }
        
        # 새로운 등록 요청인 경우
        if is_registration_request:
            # GPS 좌표가 있는지 확인
            if context.user_location and 'latitude' in context.user_location:
                # GPS 좌표가 있으면 주소 변환 실행
                address_result = self._get_address_from_tmap(
                    context.user_location['latitude'], 
                    context.user_location['longitude']
                )
                
                if address_result["success"]:
                    context.registration_state = "address_confirmed"
                    context.registration_data = {
                        "latitude": context.user_location['latitude'],
                        "longitude": context.user_location['longitude'],
                        "address": address_result["address"],
                        "region_name": address_result.get("region_name", "")
                    }
                    
                    return {
                        "response": f"""🚀 무선국 등록을 시작합니다!

📍 현재 위치: {context.user_location['latitude']:.6f}, {context.user_location['longitude']:.6f}
🏠 주소: {address_result['address']}
📍 지역: {address_result.get('region_name', '알 수 없음')}

이제 무선국 정보를 입력해 주세요:
• 무선국명 (예: 홍길동 아마추어 무선국)
• 무선국 종류 (예: 아마추어, 간이, 업무용)
• 담당자명
• 연락처

정보를 입력해 주세요:""",
                        "actions": [],
                        "data": {
                            "step": "info_collection",
                            "location": {
                                "latitude": context.user_location['latitude'],
                                "longitude": context.user_location['longitude'],
                                "address": address_result["address"]
                            }
                        }
                    }
                else:
                    return {
                        "response": f"주소 변환에 실패했습니다: {address_result.get('error')}",
                        "actions": ["retry", "manual_input"],
                        "data": None
                    }
            else:
                # GPS 좌표가 없으면 위치 요청
                return {
                    "response": """무선국 등록을 위해 현재 위치가 필요합니다.

📍 위치 권한을 허용해 주시거나, 주소를 직접 입력해 주세요.

예시: "서울시 강남구 테헤란로 123" """,
                    "actions": ["request_location"],
                    "data": {"step": "location_required", "auto_get_gps": True}
                }
        
        # 일반 대화
        return self._generate_fallback_response(message, context)
    
    def _generate_fallback_response(self, message: str, context: ChatContext) -> Dict[str, Any]:
        """일반 대화 처리"""
        general_responses = [
            "GPS 무선국 검사와 관련해서 도움을 드릴 수 있습니다. 무선국 검색, 등록, 근처 조회 등의 기능을 사용해 보세요.",
            "무선국 관련 업무를 지원해 드리겠습니다. '검색', '등록', '근처', '목록' 등의 키워드를 사용하시면 더 정확한 도움을 받을 수 있습니다.",
            "GPS 무선국 검사 시스템입니다. 구체적인 요청사항을 말씀해 주시면 적절한 기능으로 안내해 드리겠습니다.",
            "무선국 검사 및 관리에 대해 문의하신 것 같습니다. 어떤 작업을 도와드릴까요?",
        ]
        
        import random
        response = random.choice(general_responses)
        
        return {
            "response": response,
            "actions": ["search", "nearby_search", "register_new", "list_stations", "help"],
            "data": None
        }
    
    def get_quick_actions(self, context: ChatContext) -> List[Dict[str, str]]:
        """현재 컨텍스트에 맞는 빠른 액션 버튼 생성"""
        actions = []
        
        # GPS 위치 정보가 있는 경우
        if context.user_location:
            actions.extend([
                {"text": "🏢 등록", "action": "무선국 등록해줘"},
                {"text": "📍 위치재확인", "action": "GPS 정보 다시 확인"},
                {"text": "🔍 주변검색", "action": "내 위치 주변 무선국 검색"},
                {"text": "🔎 검색", "action": "무선국 검색해줘"},
                {"text": "📋 전체", "action": "무선국 목록 보여줘"}
            ])
        else:
            # GPS 위치 정보가 없는 경우 - GPS 획득만 가능
            actions.extend([
                {"text": "📍 GPS요청", "action": "request_location"}
            ])
        
        # 항상 기본 액션만 반환 (파생 액션 없음)
        return actions

    def clear_context(self, session_id: str) -> bool:
        """세션 컨텍스트 초기화"""
        try:
            # 캐시에서 해당 세션 관련 데이터 제거
            cache_keys = [key for key in self.cache._cache.keys() if session_id in key]
            for key in cache_keys:
                self.cache.delete(key)
            
            logger.info(f"세션 {session_id} 컨텍스트 초기화 완료")
            return True
        except Exception as e:
            logger.error(f"컨텍스트 초기화 실패: {e}")
            return False 

    def get_function_definitions(self) -> List[Dict[str, Any]]:
        """OpenAI Function Calling을 위한 함수 정의"""
        return [
            {
                "name": "getCurrentGPS",
                "description": "사용자의 현재 GPS 좌표를 획득합니다. 무선국 등록 시 위치 정보가 필요할 때 사용합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": []
                }
            },
            {
                "name": "getAddressFromTmap",
                "description": "GPS 좌표를 주소로 변환합니다. 티맵 API를 사용하여 정확한 주소 정보를 제공합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "latitude": {
                            "type": "number",
                            "description": "위도 좌표"
                        },
                        "longitude": {
                            "type": "number", 
                            "description": "경도 좌표"
                        }
                    },
                    "required": ["latitude", "longitude"]
                }
            },
            {
                "name": "saveRadioStation",
                "description": "무선국 정보를 데이터베이스에 저장합니다. 모든 필수 정보가 수집된 후 호출합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station_name": {
                            "type": "string",
                            "description": "무선국명 (필수)"
                        },
                        "station_type": {
                            "type": "string",
                            "description": "무선국 종류 (기지국, 중계소, 송신소 등)"
                        },
                        "latitude": {
                            "type": "number",
                            "description": "위도 좌표"
                        },
                        "longitude": {
                            "type": "number",
                            "description": "경도 좌표"
                        },
                        "inspector_id": {
                            "type": "string",
                            "description": "검사관 ID 또는 담당자명"
                        },
                        "station_alias": {
                            "type": "string",
                            "description": "무선국 별칭 (선택사항)"
                        },
                        "region_name": {
                            "type": "string",
                            "description": "지역명"
                        },
                        "detailed_location": {
                            "type": "string",
                            "description": "상세 위치 설명"
                        }
                    },
                    "required": ["station_name", "station_type", "latitude", "longitude", "inspector_id"]
                }
            },
            {
                "name": "updateRegistrationState",
                "description": "무선국 등록 진행 상태를 업데이트합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "state": {
                            "type": "string",
                            "enum": ["started", "location_confirmed", "info_collecting", "completed"],
                            "description": "등록 진행 상태"
                        },
                        "data": {
                            "type": "object",
                            "description": "등록 과정에서 수집된 데이터"
                        }
                    },
                    "required": ["state"]
                }
            },
            {
                "name": "parseRegistrationInfo",
                "description": "사용자 메시지에서 무선국 등록에 필요한 정보를 추출합니다.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "station_name": {
                            "type": "string",
                            "description": "무선국명"
                        },
                        "station_type": {
                            "type": "string",
                            "description": "무선국 종류 (예: 아마추어, 간이, 업무용 등)"
                        },
                        "contact_person": {
                            "type": "string",
                            "description": "담당자명"
                        },
                        "contact_phone": {
                            "type": "string",
                            "description": "연락처"
                        }
                    },
                    "required": [] # 모든 필드가 필수는 아님, 부분적으로 추출 가능
                }
            }
        ]

    def execute_function(self, function_name: str, arguments: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """OpenAI Function Calling 실행"""
        try:
            if function_name == "getCurrentGPS":
                return self._get_current_gps(context)
            elif function_name == "getAddressFromTmap":
                return self._get_address_from_tmap(arguments["latitude"], arguments["longitude"])
            elif function_name == "saveRadioStation":
                return self._save_radio_station(arguments, context)
            elif function_name == "updateRegistrationState":
                return self._update_registration_state(arguments["state"], arguments.get("data", {}), context)
            elif function_name == "parseRegistrationInfo":
                return {"success": True, "parsed_info": arguments}
            else:
                return {"success": False, "error": f"Unknown function: {function_name}"}
        except Exception as e:
            logger.error(f"Function execution error: {function_name} - {e}")
            return {"success": False, "error": str(e)}

    def _get_current_gps(self, context: ChatContext) -> Dict[str, Any]:
        """현재 GPS 좌표 획득"""
        if context.user_location:
            return {
                "success": True,
                "latitude": context.user_location["latitude"],
                "longitude": context.user_location["longitude"],
                "message": "GPS 좌표를 성공적으로 획득했습니다."
            }
        else:
            return {
                "success": False,
                "error": "GPS 위치 정보가 없습니다. 브라우저에서 위치 권한을 허용해 주세요.",
                "request_gps": True
            }

    def _get_address_from_tmap(self, latitude: float, longitude: float) -> Dict[str, Any]:
        """티맵 API를 통한 주소 변환"""
        try:
            # LocationService 사용
            address_result = self.location_service.get_address_from_coordinates(latitude, longitude)
            
            if address_result["success"]:
                return address_result
            else:
                # 실패 시 기본 정보 반환
                return {
                    "success": False,
                    "error": address_result.get("error", "주소 변환에 실패했습니다."),
                    "latitude": latitude,
                    "longitude": longitude,
                    "fallback_address": f"위도 {latitude:.6f}, 경도 {longitude:.6f}",
                    "manual_input_required": True
                }
                
        except Exception as e:
            logger.error(f"Address conversion error: {e}")
            return {
                "success": False,
                "error": "주소 변환 중 오류가 발생했습니다.",
                "latitude": latitude,
                "longitude": longitude,
                "fallback_address": f"위도 {latitude:.6f}, 경도 {longitude:.6f}",
                "manual_input_required": True
            }

    def _save_radio_station(self, data: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """무선국 정보 데이터베이스 저장"""
        try:
            from ..models.wireless_station import WirelessStation, WirelessStationDAO
            
            # 필수 필드 검증
            required_fields = ["station_name", "station_type", "latitude", "longitude", "inspector_id"]
            missing_fields = [field for field in required_fields if not data.get(field)]
            
            if missing_fields:
                return {
                    "success": False,
                    "error": f"필수 정보가 누락되었습니다: {', '.join(missing_fields)}",
                    "missing_fields": missing_fields
                }
            
            # 위치 검증
            validation_result = self.location_service.validate_registration_location(
                data["latitude"], data["longitude"], data["station_name"]
            )
            
            if not validation_result["valid"]:
                return {
                    "success": False,
                    "error": "위치 검증에 실패했습니다.",
                    "warnings": validation_result["warnings"],
                    "recommendations": validation_result["recommendations"]
                }
            
            # 누락된 필드들 자동 생성
            # station_alias가 없으면 station_name에서 생성
            if not data.get("station_alias"):
                alias_parts = []
                if "아마추어" in data["station_name"]:
                    alias_parts.append("아마추어")
                if "무선국" in data["station_name"]:
                    alias_parts.append("무선국")
                data["station_alias"] = ",".join(alias_parts) if alias_parts else data["station_name"]
            
            # tmap_address 설정 (address 또는 fallback)
            tmap_address = data.get("address", data.get("tmap_address", f"좌표: {data['latitude']:.6f}, {data['longitude']:.6f}"))
            
            # detailed_location 설정
            if not data.get("detailed_location"):
                if data.get("region_name"):
                    data["detailed_location"] = data["region_name"] + " 일대"
                else:
                    data["detailed_location"] = "GPS 좌표 기반 위치"
            
            # inspector_id 설정 (contact_person이 있으면 사용)
            inspector_id = data.get("inspector_id", data.get("contact_person", "system_user"))
            
            # WirelessStation 객체 생성
            station = WirelessStation(
                station_id="",  # 자동 생성
                station_name=data["station_name"],
                station_type=data["station_type"],
                latitude=data["latitude"],
                longitude=data["longitude"],
                inspector_id=inspector_id,
                station_alias=data["station_alias"],
                tmap_address=tmap_address,
                region_name=data.get("region_name", "알 수 없음"),
                detailed_location=data["detailed_location"],
                registration_status="진행중"
            )
            
            # 데이터베이스에 저장
            dao = WirelessStationDAO()
            station_id = dao.create_station(station)
            
            # 등록 상태 업데이트
            context.registration_state = "completed"
            
            return {
                "success": True,
                "station_id": station_id,
                "message": f"무선국 '{data['station_name']}'이 성공적으로 등록되었습니다. (등록번호: {station_id})",
                "station_data": station.to_dict(),
                "validation_info": validation_result
            }
            
        except Exception as e:
            logger.error(f"Radio station save error: {e}")
            return {
                "success": False,
                "error": "무선국 저장 중 오류가 발생했습니다.",
                "details": str(e),
                "retry_recommended": True
            }

    def _update_registration_state(self, state: str, data: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """등록 상태 업데이트"""
        try:
            context.registration_state = state
            context.registration_data.update(data)
            
            return {
                "success": True,
                "state": state,
                "message": f"등록 상태가 '{state}'로 업데이트되었습니다."
            }
        except Exception as e:
            logger.error(f"Registration state update error: {e}")
            return {
                "success": False,
                "error": "상태 업데이트 중 오류가 발생했습니다."
            }

    def _parse_registration_info(self, message: str) -> Dict[str, Any]:
        """사용자 입력에서 무선국 등록 정보 추출 (OpenAI API 폴백용)"""
        import re
        
        info = {}
        message_lower = message.lower()
        
        # 슬래시로 구분된 형식 (예: 빛포구항 / 간이 / 정백철 / 1565) 처리
        # 이 형식은 무선국명 / 종류 / 담당자명 / 연락처 순서로 가정
        parts = [p.strip() for p in message.split('/')]
        if len(parts) >= 4:
            info['station_name'] = parts[0]
            info['station_type'] = parts[1]
            info['contact_person'] = parts[2]
            info['contact_phone'] = parts[3]
            return info # 슬래시 형식으로 파싱 성공 시 바로 반환

        # 무선국명 추출 (첫 번째 콤마 앞의 텍스트 또는 "무선국명" 키워드 뒤)
        station_name_patterns = [
            r'무선국명[:\s]*([^,\n]+)',
            r'^([^,]+)(?=,)'  # 첫 번째 콤마 앞의 텍스트
        ]
        
        for pattern in station_name_patterns:
            match = re.search(pattern, message.strip())
            if match:
                info['station_name'] = match.group(1).strip()
                break
        
        # 무선국 종류 추출
        station_type_patterns = [
            r'(?:무선국\s*)?종류[:\s]*([^,\n]+)',
            r'(아마추어|간이|업무용|실험국|특수국)',
            r'종류[:\s]*([^,\n]+)'
        ]
        
        for pattern in station_type_patterns:
            match = re.search(pattern, message)
            if match:
                info['station_type'] = match.group(1).strip()
                break
        
        # 담당자 정보 추출
        contact_patterns = [
            r'담당자[:\s]*(?:는\s*)?([^,\n]+)',
            r'책임자[:\s]*([^,\n]+)',
            r'관리자[:\s]*([^,\n]+)'
        ]
        
        for pattern in contact_patterns:
            match = re.search(pattern, message)
            if match:
                info['contact_person'] = match.group(1).strip()
                break
        
        # 연락처 추출
        phone_patterns = [
            r'연락처[:\s]*(?:는\s*)?([0-9\-\s]+)',
            r'전화번호[:\s]*([0-9\-\s]+)',
            r'(?:번호[:\s]*)?([0-9]{2,3}[-\s]?[0-9]{3,4}[-\s]?[0-9]{4})'
        ]
        
        for pattern in phone_patterns:
            match = re.search(pattern, message)
            if match:
                info['contact_phone'] = match.group(1).strip()
                break
        
        return info

    def _handle_registration_info_action(self, action_result: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """등록 정보 입력 처리"""
        try:
            message = action_result.get('message', '')
            
            # 기존 등록 데이터에 파싱된 정보 병합
            if not hasattr(context, 'registration_data'):
                context.registration_data = {}

            # OpenAI API를 사용하여 정보 파싱 시도
            if self.client_available:
                try:
                    # 시스템 프롬프트와 현재까지 수집된 등록 정보 제공
                    # parseRegistrationInfo 함수만 사용하도록 tools를 제한
                    messages = [{"role": "system", "content": self.get_system_prompt() + "\n\n현재까지 수집된 무선국 등록 정보: " + json.dumps(context.registration_data, ensure_ascii=False)}]
                    messages.append({"role": "user", "content": message})

                    response = self.openai_client.chat.completions.create(
                        model=self.openai_model,
                        messages=messages,
                        functions=[f for f in self.get_function_definitions() if f["name"] == "parseRegistrationInfo"], # parseRegistrationInfo 함수만 전달
                        function_call={"name": "parseRegistrationInfo"}, # parseRegistrationInfo 함수를 강제로 호출
                        max_tokens=500,
                        temperature=0.0 # 정확한 파싱을 위해 낮은 온도 설정
                    )
                    
                    response_message = response.choices[0].message
                    if response_message.function_call and response_message.function_call.name == "parseRegistrationInfo":
                        parsed_info_from_openai = json.loads(response_message.function_call.arguments)
                        logger.info(f"OpenAI를 통해 파싱된 정보: {parsed_info_from_openai}")
                        context.registration_data.update(parsed_info_from_openai)
                    else:
                        logger.warning("OpenAI가 parseRegistrationInfo를 호출하지 않음. 로컬 파싱 시도.")
                        # OpenAI가 함수 호출을 하지 않으면 로컬 파싱으로 폴백
                        parsed_info = self._parse_registration_info(message)
                        context.registration_data.update(parsed_info)
                except Exception as e:
                    logger.error(f"OpenAI 파싱 중 오류 발생: {e}. 로컬 파싱으로 폴백.")
                    # 오류 발생 시 로컬 파싱으로 폴백
                    parsed_info = self._parse_registration_info(message)
                    context.registration_data.update(parsed_info)
            else:
                # OpenAI 클라이언트가 사용 불가능하면 로컬 파싱
                parsed_info = self._parse_registration_info(message)
                context.registration_data.update(parsed_info)
            
            # 필수 정보 확인
            required_fields = {
                'station_name': '무선국명',
                'station_type': '무선국 종류',
                'contact_person': '담당자명',
                'contact_phone': '연락처'
            }
            
            missing_fields = []
            for field, korean_name in required_fields.items():
                if not context.registration_data.get(field):
                    missing_fields.append(korean_name)
            
            if missing_fields:
                # 부족한 정보 요청
                return {
                    "response": f"""입력해 주신 정보를 확인했습니다.

✅ 입력된 정보:
{self._format_registration_info(context.registration_data)}

❌ 누락된 정보: {', '.join(missing_fields)}

누락된 정보를 추가로 입력해 주세요:""",
                    "data": {
                        "step": "info_collection_partial",
                        "missing_fields": missing_fields,
                        "current_info": context.registration_data
                    }
                }
            else:
                # 모든 정보가 있으면 등록 실행
                return self._execute_station_registration(context)
                
        except Exception as e:
            logger.error(f"등록 정보 처리 오류: {e}")
            return {
                "response": "등록 정보 처리 중 오류가 발생했습니다. 다시 시도해 주세요.",
                "data": {"error": str(e)}
            }

    def _format_registration_info(self, info: Dict[str, Any]) -> str:
        """등록 정보를 보기 좋게 포맷팅"""
        formatted = []
        if info.get('station_name'):
            formatted.append(f"• 무선국명: {info['station_name']}")
        if info.get('station_type'):
            formatted.append(f"• 종류: {info['station_type']}")
        if info.get('contact_person'):
            formatted.append(f"• 담당자: {info['contact_person']}")
        if info.get('contact_phone'):
            formatted.append(f"• 연락처: {info['contact_phone']}")
        
        return '\n'.join(formatted) if formatted else "입력된 정보가 없습니다."

    def _execute_station_registration(self, context: ChatContext) -> Dict[str, Any]:
        """무선국 등록 실행"""
        try:
            # 등록 데이터 준비
            registration_data = {
                "station_name": context.registration_data.get('station_name'),
                "station_type": context.registration_data.get('station_type'),
                "latitude": context.registration_data.get('latitude'),
                "longitude": context.registration_data.get('longitude'),
                "address": context.registration_data.get('address', ''),
                "region_name": context.registration_data.get('region_name', ''),
                "contact_person": context.registration_data.get('contact_person'),
                "contact_phone": context.registration_data.get('contact_phone'),
                "inspector_id": context.registration_data.get('contact_person', 'system_user'),  # 담당자명으로 설정
                "status": "active"
            }
            
            # saveRadioStation 함수 실행
            save_result = self._save_radio_station(registration_data, context)
            
            if save_result["success"]:
                # 등록 성공
                context.registration_state = "completed"
                
                return {
                    "response": f"""🎉 무선국 등록이 완료되었습니다!

📋 등록된 정보:
• 무선국명: {registration_data['station_name']}
• 종류: {registration_data['station_type']}
• 위치: {registration_data['latitude']:.6f}, {registration_data['longitude']:.6f}
• 주소: {registration_data['address']}
• 담당자: {registration_data['contact_person']}
• 연락처: {registration_data['contact_phone']}

등록이 성공적으로 완료되었습니다! 🚀""",
                    "data": {
                        "step": "completed",
                        "registered_station": registration_data,
                        "station_id": save_result.get('station_id')
                    }
                }
            else:
                # 등록 실패
                return {
                    "response": f"""❌ 무선국 등록에 실패했습니다.

오류 내용: {save_result.get('error', '알 수 없는 오류')}

다시 시도하시겠습니까?""",
                    "data": {
                        "step": "registration_failed",
                        "error": save_result.get('error'),
                        "registration_data": registration_data
                    }
                }
                
        except Exception as e:
            logger.error(f"무선국 등록 실행 오류: {e}")
            return {
                "response": "무선국 등록 중 오류가 발생했습니다. 다시 시도해 주세요.",
                "data": {"error": str(e)}
            }

    def _handle_address_search_action(self, action_result: Dict[str, Any], context: ChatContext) -> Dict[str, Any]:
        """주소 검색 액션 처리"""
        try:
            from ..services.location_service import get_location_service
            location_service = get_location_service()
            
            address = action_result.get('address', '')
            
            # "주소로 좌표 찾기:" 접두사 제거
            if address.startswith('주소로 좌표 찾기:'):
                address = address.replace('주소로 좌표 찾기:', '').strip()
            
            if not address:
                return {
                    "response": "❌ 검색할 주소를 입력해 주세요.\n\n예시: 서울시 강남구 테헤란로 123",
                    "actions": [
                        {"action": "주소로 좌표 찾기", "text": "🏠 주소 재입력"},
                        {"action": "수동 좌표 입력", "text": "✏️ 수동 좌표 입력"}
                    ]
                }
            
            # 주소를 좌표로 변환
            result = location_service.get_coordinates_from_address(address)
            
            if result["success"]:
                # 성공 시 좌표 정보 업데이트
                context.user_location = {
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                    "accuracy": 0,  # 주소 검색이므로 정확도는 0
                    "manual": True,
                    "source": "address_search"
                }
                
                response_text = f"✅ 주소 검색 성공!\n\n"
                response_text += f"📍 입력 주소: {result['address']}\n"
                response_text += f"🗺️ 변환된 좌표: {result['latitude']:.6f}, {result['longitude']:.6f}\n"
                
                if result.get('region_name'):
                    response_text += f"📍 지역: {result['region_name']}\n"
                
                response_text += f"🎯 정확도: {result.get('accuracy', 'medium')}\n\n"
                response_text += "이제 무선국 등록을 시작할 수 있습니다!"
                
                return {
                    "response": response_text,
                    "data": {
                        "location": {
                            "latitude": result["latitude"],
                            "longitude": result["longitude"],
                            "address": result["address"],
                            "region": result.get("region_name")
                        }
                    },
                    "actions": [
                        {"action": "무선국 등록해줘", "text": "🏢 무선국 등록"},
                        {"action": "내 위치 주변 무선국 검색", "text": "🔍 주변 무선국"},
                        {"action": "다른 주소 검색", "text": "🏠 다른 주소 검색"}
                    ]
                }
            else:
                # 실패 시 오류 메시지 및 대안 제공
                error_message = f"❌ 주소 검색 실패\n\n{result.get('error', '알 수 없는 오류')}"
                
                if result.get('suggestions'):
                    error_message += "\n\n💡 검색 팁:\n"
                    for suggestion in result['suggestions']:
                        error_message += f"• {suggestion}\n"
                
                return {
                    "response": error_message,
                    "actions": [
                        {"action": "주소로 좌표 찾기", "text": "🏠 다시 검색"},
                        {"action": "수동 좌표 입력", "text": "✏️ 수동 좌표 입력"},
                        {"action": "request_location", "text": "📍 GPS 재요청"}
                    ]
                }
                
        except Exception as e:
            logger.error(f"주소 검색 처리 오류: {e}")
            return {
                "response": f"❌ 주소 검색 중 오류가 발생했습니다.\n\n오류 내용: {str(e)}",
                "actions": [
                    {"action": "주소로 좌표 찾기", "text": "🏠 다시 시도"},
                    {"action": "수동 좌표 입력", "text": "✏️ 수동 입력"}
                ]
            }

    def _handle_reconfirm_gps_action(self, context: ChatContext) -> Dict[str, Any]:
        """GPS 정보 다시 확인 액션 처리"""
        if not context.user_location:
            return {
                "response": "현재 저장된 위치 정보가 없습니다. GPS를 새로 획득하거나 주소를 입력해 주세요.",
                "actions": ["request_location", "주소로 좌표 찾기"],
                "data": None
            }
        
        latitude = context.user_location['latitude']
        longitude = context.user_location['longitude']
        
        try:
            pinpoint_info = self.location_service.get_current_pinpoint_info(latitude, longitude)
            
            if pinpoint_info["success"]:
                address_info = pinpoint_info.get("address_info", {})
                nearby_summary = pinpoint_info.get("nearby_stations_summary", {})
                validation_result = pinpoint_info.get("validation_result", {})
                
                response_text = f"📍 현재 핀포인트 정보:\n\n"
                response_text += f"🗺️ 좌표: {latitude:.6f}, {longitude:.6f}\n"
                
                if address_info and address_info.get("address"):
                    response_text += f"🏠 주소: {address_info['address']}\n"
                    if address_info.get("detailed_location"):
                        response_text += f"   (상세: {address_info['detailed_location']})\n"
                else:
                    response_text += "🏠 주소 정보: 변환 실패\n"
                
                response_text += f"\n✅ 위치 유효성: {'유효함' if validation_result.get('is_valid') else '문제 있음'}\n"
                if validation_result.get('accuracy_meters') is not None:
                    response_text += f"   정확도: {validation_result['accuracy_meters']:.1f}m ({validation_result.get('confidence_level')})\n"
                if validation_result.get('warnings'):
                    response_text += "   경고: " + ", ".join(validation_result['warnings']) + "\n"
                if validation_result.get('suggestions'):
                    response_text += "   제안: " + ", ".join(validation_result['suggestions']) + "\n"
                
                response_text += f"\n🔍 주변 무선국: 총 {nearby_summary.get('total_count', 0)}개 (반경 {nearby_summary.get('search_radius', self.location_service.default_search_radius)}m)\n"
                
                if nearby_summary.get('total_count', 0) > 0:
                    response_text += "   가까운 무선국:\n"
                    for i, station in enumerate(nearby_summary['all_stations'][:3], 1): # 최대 3개만 표시
                        response_text += f"   {i}. {station['station_name']} ({station['distance_meters']:.1f}m)\n"
                else:
                    response_text += "   주변에 등록된 무선국이 없습니다.\n"
                
                return {
                    "response": response_text,
                    "actions": ["nearby_search", "register_new", "search"],
                    "data": pinpoint_info
                }
            else:
                return {
                    "response": f"핀포인트 정보를 가져오는 데 실패했습니다: {pinpoint_info.get('message', '알 수 없는 오류')}",
                    "actions": ["request_location", "주소로 좌표 찾기"],
                    "data": None
                }
        except Exception as e:
            logger.error(f"GPS 재확인 처리 오류: {e}")
            return {
                "response": f"GPS 정보 재확인 중 오류가 발생했습니다: {str(e)}",
                "actions": ["request_location", "주소로 좌표 찾기"],
                "data": None
            }
