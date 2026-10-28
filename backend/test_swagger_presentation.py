"""Kiểm tra Swagger tách hai chế độ mà không thay đổi các endpoint nghiệp vụ."""
import os
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
from swagger_presentation import install_swagger_presentation


class LoginData(BaseModel):
    email: str
    password: str


class DemoFallData(BaseModel):
    device_id: str
    confidence: float = 0.95


def create_app():
    """Tạo API tối thiểu đại diện cho FallGuard, không chạm DB người dùng."""
    app = FastAPI(docs_url=None, redoc_url=None)

    @app.post('/auth/login')
    def login(data: LoginData):
        return {'access_token': 'test-only', 'token_type': 'bearer'}

    @app.get('/devices')
    def devices():
        return [{'device_id': 'DEV-001'}]

    @app.post('/admin/api/demo/fall')
    def fall(data: DemoFallData, authorization: str | None = Header(default=None)):
        if authorization != 'Bearer admin-test':
            raise HTTPException(status_code=403)
        return {'event_id': 1}

    @app.get('/internal-secret-test')
    def internal():
        return {'test': True}

    install_swagger_presentation(app)
    return app


def test_swagger():
    os.environ['APP_ENV'] = 'development'
    app = create_app()
    client = TestClient(app, client=('127.0.0.1', 50000))
    assert client.get('/docs').status_code == 200
    assert client.get('/docs/full').status_code == 200
    demo = client.get('/openapi-demo.json').json()
    full = client.get('/openapi-full.json').json()
    assert '/auth/login' in demo['paths']
    assert '/devices' in demo['paths']
    assert '/admin/api/demo/fall' in demo['paths']
    assert '/internal-secret-test' not in demo['paths']
    assert '/internal-secret-test' in full['paths']
    assert demo['paths']['/admin/api/demo/fall']['post']['requestBody']['content']['application/json']['example'] == {'device_id': 'DEV-001', 'confidence': 0.95}
    assert client.post('/admin/api/demo/fall', json={'device_id': 'DEV-001'}).status_code == 403
    assert client.post('/admin/api/demo/fall', json={'device_id': 'DEV-001'}, headers={'Authorization': 'Bearer admin-test'}).status_code == 200
    os.environ['APP_ENV'] = 'production'
    assert client.get('/docs').status_code == 404
    assert client.get('/openapi-demo.json').status_code == 404
    os.environ['APP_ENV'] = 'development'
    print('SWAGGER PRESENTATION TEST: PASS')


if __name__ == '__main__':
    test_swagger()
