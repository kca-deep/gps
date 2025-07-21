"""
GPS 무선국 검사 AI 채팅 시스템 - Flask 백엔드

메인 애플리케이션 엔트리포인트
"""

import os
import sys
import logging
from datetime import datetime
from logging.handlers import TimedRotatingFileHandler
from flask import Flask, jsonify, render_template, send_from_directory
from flask_cors import CORS
from dotenv import load_dotenv

# Flask-CORS가 없을 경우를 대비한 안전한 import
try:
    from flask_cors import CORS
    HAS_CORS = True
except ImportError:
    HAS_CORS = False
    print("Flask-CORS가 설치되지 않았습니다. CORS 없이 실행합니다.")

# 프로젝트 루트를 Python path에 추가
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from config.settings import get_config
from src.gps_inspection.controllers.chat_controller import chat_bp
from src.gps_inspection.controllers.search_controller import search_bp
from src.gps_inspection.controllers.station_controller import station_bp
from src.gps_inspection.models.database import DatabaseManager

# 환경 변수 로드
load_dotenv()

def setup_logging():
    """로깅 설정 - 날짜별 파일 생성"""
    # logs 디렉토리가 없으면 생성
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # 날짜별 로그 파일명 생성
    current_date = datetime.now().strftime('%Y%m%d')
    log_filename = f'logs/log_{current_date}.log'
    
    # 루트 로거 설정
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    
    # 기존 핸들러 제거
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # 파일 핸들러 설정 (일일 로테이션)
    file_handler = TimedRotatingFileHandler(
        log_filename,
        when='midnight',
        interval=1,
        backupCount=30,  # 30일간 보관
        encoding='utf-8'
    )
    file_handler.setLevel(logging.INFO)
    
    # 콘솔 핸들러 설정
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 포맷터 설정
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 핸들러 추가
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)
    
    # Werkzeug 로거 레벨 조정 (개발 모드에서 너무 많은 로그 방지)
    logging.getLogger('werkzeug').setLevel(logging.WARNING)
    
    logging.info(f"로깅 시스템 초기화 완료 - 로그 파일: {log_filename}")

def create_app():
    """Flask 애플리케이션 팩토리"""
    app = Flask(__name__, template_folder='templates', static_folder='static')
    
    # 설정 로드
    config = get_config()
    
    # 설정 검증
    openai_key = os.getenv('OPENAI_API_KEY')
    if not openai_key or openai_key.strip() == '' or openai_key == 'your_openai_api_key_here':
        print("⚠️  설정 검증 실패: OPENAI_API_KEY is required")
        print("기본 설정으로 계속 진행합니다.")
    
    # Flask 설정
    app.config.update(
        SECRET_KEY=config.SECRET_KEY,
        DEBUG=config.DEBUG,
        # JSON 한글 깨짐 방지
        JSON_AS_ASCII=False,
        JSONIFY_PRETTYPRINT_REGULAR=True
    )
    
    # CORS 설정
    CORS(app, resources={
        r"/api/*": {
            "origins": ["http://localhost:5000", "http://127.0.0.1:5000"],
            "methods": ["GET", "POST", "PUT", "DELETE", "OPTIONS"],
            "allow_headers": ["Content-Type", "Authorization"]
        }
    })
    
    logger = logging.getLogger(__name__)
    
    # 데이터베이스 초기화
    try:
        db_manager = DatabaseManager()
        logger.info("데이터베이스 초기화 완료")
    except Exception as e:
        logger.error(f"데이터베이스 초기화 실패: {e}")
        raise
    
    # Blueprint 등록
    app.register_blueprint(station_bp, url_prefix='/api/stations')
    app.register_blueprint(search_bp, url_prefix='/api/search')
    app.register_blueprint(chat_bp, url_prefix='/api/chat')
    
    # 메인 페이지 라우트 - 선박검사 시스템 홈
    @app.route('/')
    def index():
        """선박검사 시스템 메인 페이지"""
        try:
            # 시스템 상태 정보 수집
            db_manager = DatabaseManager()
            db_status = "연결됨"
            
            # OpenAI 서비스 상태 확인
            openai_key = os.getenv('OPENAI_API_KEY')
            if openai_key and openai_key != 'your_openai_api_key_here':
                ai_status = "운영 중"
            else:
                ai_status = "모의 모드"
            
            status_data = {
                "service": "실행 중",
                "version": "2.0.0",
                "database": db_status,
                "ai_service": ai_status,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return render_template('index.html', status=status_data)
            
        except Exception as e:
            logger.error(f"메인 페이지 로드 실패: {e}")
            # 오류 발생 시 기본 정보 반환
            status_data = {
                "service": "오류",
                "version": "2.0.0",
                "database": "오류",
                "ai_service": "오류",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            return render_template('index.html', status=status_data)
    
    # API 문서 페이지 (기존 문서 유지)
    @app.route('/api-docs')
    def api_docs():
        """API 문서 페이지"""
        try:
            # 시스템 상태 정보 수집
            db_manager = DatabaseManager()
            db_status = "연결됨"
            
            # OpenAI 서비스 상태 확인
            openai_key = os.getenv('OPENAI_API_KEY')
            if openai_key and openai_key != 'your_openai_api_key_here':
                ai_status = "운영 중"
            else:
                ai_status = "모의 모드"
            
            status_data = {
                "service": "실행 중",
                "version": "2.0.0",
                "database": db_status,
                "ai_service": ai_status,
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            return render_template('api_docs.html', status=status_data)
            
        except Exception as e:
            logger.error(f"API 문서 페이지 로드 실패: {e}")
            # 오류 발생 시 기본 정보 반환
            status_data = {
                "service": "오류",
                "version": "2.0.0",
                "database": "오류",
                "ai_service": "오류",
                "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            return render_template('api_docs.html', status=status_data)

    # JSON API 정보 (API 호출용)
    @app.route('/api/info')
    def api_info():
        """시스템 정보 JSON API"""
        return jsonify({
            "service": "AI기반 선박검사 위치정보 수집시스템",
            "version": "2.0.0",
            "status": "running",
            "endpoints": {
                "main": "/",
                "chat_ui": "/chat",
                "api_docs": "/api-docs",
                "api_inspections": "/api/inspections",
                "api_search": "/api/search",
                "api_chat": "/api/chat",
                "health": "/health"
            },
            "features": [
                "선박 정보 지능형 검색 (IMO, 선박명)",
                "위치 기반 검사 구역 관리",
                "AI 기반 검사 어시스턴트",
                "실시간 음성 입력 지원",
                "검사 일정 충돌 확인"
            ],
            "timestamp": datetime.now().isoformat()
        })
    
    # 채팅 UI 페이지
    @app.route('/chat')
    def chat_ui():
        """채팅 UI 페이지"""
        return render_template('chat.html')
    
    # 정적 파일 서비스
    @app.route('/static/<path:filename>')
    def static_files(filename):
        """정적 파일 서비스"""
        return send_from_directory('static', filename)
    
    # 헬스 체크
    @app.route('/health')
    def health_check():
        """시스템 상태 확인"""
        try:
            # 데이터베이스 연결 확인
            db_manager = DatabaseManager()
            db_status = "connected"
            
            # OpenAI API 키 확인
            openai_status = "configured" if openai_key and openai_key != 'your_openai_api_key_here' else "mock_mode"
            
            return jsonify({
                "status": "healthy",
                "timestamp": datetime.now().isoformat(),
                "components": {
                    "database": db_status,
                    "openai": openai_status,
                    "cache": "active",
                    "search": "active",
                    "location": "active"
                },
                "config": {
                    "debug": config.DEBUG,
                    "log_level": config.LOG_LEVEL,
                    "database_path": config.DATABASE_PATH
                }
            }), 200
        except Exception as e:
            logger.error(f"헬스 체크 실패: {e}")
            return jsonify({
                "status": "unhealthy",
                "error": str(e),
                "timestamp": datetime.now().isoformat()
            }), 500
    
    # 에러 핸들러
    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": "Not Found",
            "message": "요청한 리소스를 찾을 수 없습니다.",
            "available_endpoints": [
                "/", "/chat", "/health", 
                "/api/info", "/api/stations", "/api/search", "/api/chat"
            ]
        }), 404
    
    @app.errorhandler(500)
    def internal_error(error):
        logger.error(f"내부 서버 오류: {error}")
        return jsonify({
            "error": "Internal Server Error",
            "message": "내부 서버 오류가 발생했습니다."
        }), 500
    
    logger.info("Flask 애플리케이션 초기화 완료")
    return app


if __name__ == '__main__':
    # 먼저 로깅 설정
    setup_logging()
    
    app = create_app()
    
    print("🚀 GPS 무선국 검사 AI 채팅 시스템 시작")
    print(f"   서버 주소: http://127.0.0.1:5000")
    print(f"   📚 API 문서: http://127.0.0.1:5000/")
    print(f"   💬 채팅 UI: http://127.0.0.1:5000/chat")
    print(f"   🔍 헬스 체크: http://127.0.0.1:5000/health")
    print(f"   디버그 모드: {app.config['DEBUG']}")
    
    app.run(
        host='127.0.0.1',
        port=5000,
        debug=True,
        use_reloader=True
    ) 