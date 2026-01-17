# Dashboard Authentication Implementation Plan

## Goal
Implement a simple login mechanism for the Streamlit dashboard (`app.py`) to restrict access. Credentials will be stored in the existing `.env` file.

## User Review Required
> [!IMPORTANT]
> This is a basic authentication method. It is secure enough for a personal dashboard protected by HTTPS (AWS), but it does not use a database or advanced session management.

## Proposed Changes

### Configuration
#### [MODIFY] [.env.template](file:///d:/03.%EA%B0%9C%EB%B0%9C%EC%9E%90%EB%A3%8C/myupbit01/.env.template)
- Add `WEB_USERNAME` and `WEB_PASSWORD` placeholders.

### Source Code
#### [MODIFY] [app.py](file:///d:/03.%EA%B0%9C%EB%B0%9C%EC%9E%90%EB%A3%8C/myupbit01/src/myupbit01/app.py)
1.  **Add `check_password()` function**:
    - Checks `st.session_state["password_correct"]`.
    - Renders a login form if not authenticated.
    - Validates input against `os.getenv("WEB_USERNAME")` and `os.getenv("WEB_PASSWORD")`.
2.  **Integrate into `main()`**:
    - Call `check_password()` at the very beginning of `main()`.
    - If it returns `False`, stop execution (`st.stop()` or return).
3.  **Add Logout Button**:
    - Add a "Logout" button in the sidebar that clears session state and reruns.

## Verification Plan

### Manual Verification
1.  **Setup**:
    - Update `.env` with a test username/password (e.g., `admin` / `1234`).
2.  **Test Login**:
    - Run `streamlit run src/myupbit01/app.py`.
    - Verify that the dashboard content is HIDDEN and a login form is shown.
    - Enter wrong password -> verify error message.
    - Enter correct password -> verify dashboard loads.
3.  **Test Logout**:
    - Click "Logout" in sidebar -> verify return to login screen.
4.  **Deployment**:
    - Deployment to AWS will require the user to update their `.env` on the server.
