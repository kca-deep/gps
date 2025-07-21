"""
채팅 관련 API 컨트롤러

AI 채팅 기능, 세션 관리, 메시지 처리 등의 API 엔드포인트 제공
"""

from flask import Blueprint, request, jsonify
import logging
from datetime import datetime
from typing import Dict, Any, Optional

from ..services.openai_service import OpenAIService, ChatContext
from ..services.search_service import get_search_service
from ..services.location_service import get_location_service
from ..models.database import DatabaseManager

logger = logging.getLogger(__name__)

chat_bp = Blueprint('chat', __name__)

# 세션 저장소 (실제 운영에서는 Redis 등 사용)
chat_sessions: Dict[str, ChatContext] = {}

# 서비스 인스턴스 캐시 (lazy loading)
_openai_service = None
_search_service = None
_location_service = None

def get_openai_service():
    """OpenAI 서비스 인스턴스를 lazy loading으로 반환"""
    global _openai_service
    if _openai_service is None:
        _openai_service = OpenAIService()
    return _openai_service

def get_cached_search_service():
    """검색 서비스 인스턴스를 lazy loading으로 반환"""
    global _search_service
    if _search_service is None:
        _search_service = get_search_service()
    return _search_service

def get_cached_location_service():
    """위치 서비스 인스턴스를 lazy loading으로 반환"""
    global _location_service
    if _location_service is None:
        _location_service = get_location_service()
    return _location_service

@chat_bp.route('/session', methods=['POST'])
def create_session():
    """새로운 채팅 세션 생성"""
    try:
        data = request.get_json() or {}
        session_id = data.get('session_id') or f"session_{datetime.now().timestamp()}"
        
        # 사용자 위치 정보 가져오기
        user_location = None
        if 'location' in data:
            location = data['location']
            if 'latitude' in location and 'longitude' in location:
                user_location = {
                    'latitude': float(location['latitude']),
                    'longitude': float(location['longitude'])
                }
        
        # 새로운 채팅 컨텍스트 생성
        context = ChatContext(
            session_id=session_id,
            user_location=user_location
        )
        
        chat_sessions[session_id] = context
        
        # 세션 시작 메시지
        welcome_message = """🚀 GPS 무선국 검사 AI 채팅 시스템에 오신 것을 환영합니다!

저는 GPS 무선국 등록, 검사, 관리를 도와드리는 AI 어시스턴트입니다.

다음과 같은 기능을 사용하실 수 있습니다:
• 무선국 검색 및 조회
• 근처 무선국 찾기
• 새로운 무선국 등록
• 위치 기반 중복 확인

무엇을 도와드릴까요?"""
        
        # 빠른 액션 버튼 생성
        openai_service = get_openai_service()
        quick_actions = openai_service.get_quick_actions(context)
        
        response_data = {
            "session_id": session_id,
            "message": welcome_message,
            "actions": quick_actions,
            "user_location": user_location,
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"새 채팅 세션 생성: {session_id}")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"세션 생성 실패: {e}")
        return jsonify({"error": "세션 생성 중 오류가 발생했습니다"}), 500

@chat_bp.route('/message', methods=['POST'])
def send_message():
    """메시지 처리 및 응답 생성"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "요청 데이터가 없습니다"}), 400
        
        session_id = data.get('session_id')
        message = data.get('message', '').strip()
        
        if not session_id or not message:
            return jsonify({"error": "세션 ID와 메시지는 필수입니다"}), 400
        
        # 세션 컨텍스트 가져오기
        context = chat_sessions.get(session_id)
        if not context:
            # 새 세션 생성
            context = ChatContext(session_id=session_id)
            chat_sessions[session_id] = context
        
        # 사용자 위치 업데이트 (있을 경우)
        if 'location' in data:
            location = data['location']
            if 'latitude' in location and 'longitude' in location:
                context.user_location = {
                    'latitude': float(location['latitude']),
                    'longitude': float(location['longitude'])
                }
        
        # OpenAI 서비스로 메시지 처리
        openai_service = get_openai_service()
        response = openai_service.process_message(message, context)
        
        # 응답에 추가 정보 포함
        response_data = {
            "session_id": session_id,
            "user_message": message,
            "response": response['response'],
            "actions": response.get('actions', []),
            "data": response.get('data'),
            "timestamp": datetime.now().isoformat()
        }
        
        # 오류 정보가 있으면 포함
        if 'error' in response:
            response_data['error'] = response['error']
        
        logger.info(f"메시지 처리 완료: {session_id} - {len(message)} chars")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"메시지 처리 실패: {e}")
        return jsonify({
            "error": "메시지 처리 중 오류가 발생했습니다",
            "details": str(e)
        }), 500

@chat_bp.route('/quick-actions', methods=['GET'])
def get_quick_actions():
    """현재 컨텍스트에 맞는 빠른 액션 버튼 제공"""
    try:
        session_id = request.args.get('session_id')
        if not session_id:
            return jsonify({"error": "세션 ID가 필요합니다"}), 400
        
        context = chat_sessions.get(session_id)
        if not context:
            # 기본 액션 반환
            context = ChatContext(session_id=session_id)
        
        openai_service = get_openai_service()
        quick_actions = openai_service.get_quick_actions(context)
        
        return jsonify({
            "session_id": session_id,
            "actions": quick_actions,
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"빠른 액션 조회 실패: {e}")
        return jsonify({"error": "빠른 액션 조회 중 오류가 발생했습니다"}), 500

@chat_bp.route('/action', methods=['POST'])
def handle_action():
    """빠른 액션 처리"""
    try:
        data = request.get_json()
        logger.info(f"빠른 액션 요청 받음: {data}")
        
        if not data:
            return jsonify({"error": "요청 데이터가 없습니다"}), 400
        
        session_id = data.get('session_id')
        action = data.get('action')
        
        logger.info(f"액션 처리: session_id={session_id}, action={action}")
        
        if not session_id or not action:
            return jsonify({"error": "세션 ID와 액션은 필수입니다"}), 400
        
        # 세션 컨텍스트 가져오기
        context = chat_sessions.get(session_id)
        if not context:
            context = ChatContext(session_id=session_id)
            chat_sessions[session_id] = context
        
        # 액션을 메시지로 변환
        action_messages = {
            'search': '무선국 검색',
            'nearby': '근처 무선국 조회',
            'register': '새 무선국 등록',
            'list': '무선국 목록 보기',
            'help': '도움말',
            'view_details': '검색 결과 상세보기',
            'nearby_here': '현 위치 기준 검색',
            'confirm_location': '위치 확인 완료',
            'manual_location': '수동 위치 입력',
            'cancel_registration': '등록 취소',
            'continue_registration': '등록 계속하기',
            'register_another': '다른 무선국 등록',
            'view_station': '등록된 무선국 보기'
        }
        
        message = action_messages.get(action, action)
        
        # 메시지 처리
        openai_service = get_openai_service()
        response = openai_service.process_message(message, context)
        
        response_data = {
            "session_id": session_id,
            "action": action,
            "response": response['response'],
            "actions": response.get('actions', []),
            "data": response.get('data'),
            "timestamp": datetime.now().isoformat()
        }
        
        logger.info(f"액션 처리 완료: {session_id} - {action}")
        logger.info(f"응답 데이터: {response_data}")
        return jsonify(response_data), 200
        
    except Exception as e:
        logger.error(f"액션 처리 실패: {e}")
        return jsonify({"error": "액션 처리 중 오류가 발생했습니다"}), 500

@chat_bp.route('/session/<session_id>', methods=['DELETE'])
def clear_session(session_id: str):
    """세션 초기화"""
    try:
        # 세션 삭제
        if session_id in chat_sessions:
            del chat_sessions[session_id]
        
        # OpenAI 서비스 캐시 초기화
        openai_service = get_openai_service()
        openai_service.clear_context(session_id)
        
        logger.info(f"세션 초기화 완료: {session_id}")
        return jsonify({
            "message": "세션이 초기화되었습니다",
            "session_id": session_id
        }), 200
        
    except Exception as e:
        logger.error(f"세션 초기화 실패: {e}")
        return jsonify({"error": "세션 초기화 중 오류가 발생했습니다"}), 500

@chat_bp.route('/sessions', methods=['GET'])
def get_active_sessions():
    """활성 세션 목록 조회"""
    try:
        active_sessions = []
        for session_id, context in chat_sessions.items():
            session_info = {
                "session_id": session_id,
                "has_location": context.user_location is not None,
                "conversation_count": len(context.conversation_history),
                "last_action": context.last_action
            }
            active_sessions.append(session_info)
        
        return jsonify({
            "active_sessions": active_sessions,
            "total_count": len(active_sessions),
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"세션 목록 조회 실패: {e}")
        return jsonify({"error": "세션 목록 조회 중 오류가 발생했습니다"}), 500

@chat_bp.route('/health', methods=['GET'])
def health_check():
    """채팅 서비스 상태 확인"""
    try:
        # OpenAI 서비스 상태 확인
        openai_service = get_openai_service()
        openai_status = "available" if openai_service.client_available else "mock_mode"
        
        # 데이터베이스 연결 확인
        try:
            db = DatabaseManager()
            db_status = "connected"
        except Exception:
            db_status = "error"
        
        return jsonify({
            "status": "healthy",
            "openai_service": openai_status,
            "database": db_status,
            "active_sessions": len(chat_sessions),
            "timestamp": datetime.now().isoformat()
        }), 200
        
    except Exception as e:
        logger.error(f"헬스 체크 실패: {e}")
        return jsonify({
            "status": "unhealthy",
            "error": str(e),
            "timestamp": datetime.now().isoformat()
        }), 500

@chat_bp.route('/pinpoint-info', methods=['POST'])
def get_pinpoint_info():
    """
    현재 핀포인트의 상세 정보 조회 API
    클라이언트로부터 위도, 경도를 받아 해당 위치의 주소 및 주변 무선국 정보를 반환
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({"error": "요청 데이터가 없습니다"}), 400
        
        latitude = data.get('latitude')
        longitude = data.get('longitude')
        search_radius = data.get('search_radius') # 선택적 파라미터
        
        if latitude is None or longitude is None:
            return jsonify({"error": "위도(latitude)와 경도(longitude)는 필수입니다"}), 400
        
        location_service = get_cached_location_service()
        
        # get_current_pinpoint_info 함수 호출
        pinpoint_info = location_service.get_current_pinpoint_info(
            float(latitude), float(longitude), search_radius
        )
        
        if pinpoint_info["success"]:
            logger.info(f"핀포인트 정보 조회 성공: {latitude}, {longitude}")
            return jsonify(pinpoint_info), 200
        else:
            logger.warning(f"핀포인트 정보 조회 실패: {latitude}, {longitude} - {pinpoint_info.get('message')}")
            return jsonify(pinpoint_info), 400 # 실패 시 400 Bad Request 반환
            
    except ValueError:
        logger.error(f"잘못된 위도/경도 형식: latitude={latitude}, longitude={longitude}")
        return jsonify({"error": "유효하지 않은 위도 또는 경도 형식입니다."}), 400
    except Exception as e:
        logger.error(f"핀포인트 정보 조회 API 오류: {e}")
        return jsonify({
            "error": "핀포인트 정보 조회 중 서버 오류가 발생했습니다",
            "details": str(e)
        }), 500
