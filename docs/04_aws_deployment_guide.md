# AWS 클라우드 배포 가이드 (Poetry 사용 위주)

이 가이드는 `myupbit01` 프로그램을 AWS(Amazon Web Services)의 가상 서버(EC2)에 배포하여 24시간 중단 없이 실행하는 방법을 설명합니다.
최신 Ubuntu 환경에 맞춰 **Poetry**를 사용하여 의존성을 관리합니다.

## 1. 개요
우리는 AWS에서 **EC2 (Elastic Compute Cloud)**라는 서비스를 사용합니다. 이 가상 서버에 접속하여 Poetry로 환경을 꾸리고 봇을 실행합니다.

## 2. 준비 사항
*   **AWS 계정**: [aws.amazon.com](https://aws.amazon.com/ko/) 회원가입. (프리 티어 활용)

---

## 3. 단계별 진행 절차

### 1단계: 서버(EC2 인스턴스) 생성하기

1.  AWS 콘솔 -> **EC2** -> **인스턴스 시작**.
2.  **이름**: `MyUpbitBot` 등 입력.
3.  **OS 이미지**: **Ubuntu** (22.04 LTS 또는 24.04 LTS).
4.  **인스턴스 유형**: **t2.micro** (프리 티어).
5.  **키 페어**: '새 키 페어 생성' -> `.pem` 파일 다운로드 및 보관.
6.  **네트워크 설정**:
    *   **보안 그룹 생성** 체크.
    *   **SSH (22)**: 허용됨.
    *   **추가 규칙**: 유형 `사용자 지정 TCP`, 포트 `8501`, 소스 `0.0.0.0/0` (대시보드 접속용).
7.  **인스턴스 시작** 클릭.

### 2단계: 서버 접속하기

1.  EC2 목록에서 인스턴스 선택 -> 상단 **'연결'** -> **'EC2 인스턴스 연결'** 탭 -> **'연결'**.
2.  웹 브라우저 터미널이 열리면 성공.

### 3단계: 환경 설정 및 코드 다운로드

터미널에서 아래 명령어들을 한 줄씩 입력하세요.

**1. 시스템 업데이트 및 필수 도구 설치**
```bash
sudo apt update
sudo apt install pipx git -y
pipx ensurepath
```

**2. 환경변수 새로고침**
```bash
source ~/.bashrc
```

**3. Poetry 설치**
```bash
pipx install poetry
```

**4. 소스 코드 다운로드**
```bash
git clone https://github.com/daboklee75/myupbit01Solution.git
cd myupbit01Solution
```

**5. 프로젝트 패키지 설치**
```bash
poetry install
```
(Poetry가 알아서 가상환경을 만들고 라이브러리를 설치합니다)

### 4단계: 설정 파일 생성

**1. .env 파일 생성**
```bash
nano .env
```
편집기가 열리면 아래 내용을 입력하고, **실제 키 값으로 변경**하세요.

```ini
UPBIT_ACCESS_KEY=여기에_엑세스_키_입력
UPBIT_SECRET_KEY=여기에_시크릿_키_입력
```
*   저장: `Ctrl + X` -> `Y` -> `Enter`.

**2. 로그 폴더 생성**
```bash
mkdir -p logs
```

### 5단계: 프로그램 실행 (간편 스크립트)

`run.sh` 스크립트를 사용하면 기존 프로세스를 종료하고 자동으로 재시작해줍니다.

**1. 실행 권한 부여 (최초 1회)**
```bash
chmod +x run.sh
```

**2. 프로그램 시작/재시작**
```bash
./run.sh
```
실행 후 "Trader started" 등의 메시지가 뜨면 성공입니다.

### 6단계: 실행 확인 및 접속

1.  **로그 확인**:
    ```bash
    tail -f logs/trader.log
    ```
    (종료: `Ctrl + C`)

2.  **대시보드 접속**:
    *   브라우저 주소창: `http://[퍼블릭IP]:8501`

### 참고: 프로그램 종료 방법
`run.sh`를 실행하면 자동으로 재시작되지만, 아예 끄고 싶을 때는:
```bash
pkill -f trader.py
pkill -f streamlit
```
