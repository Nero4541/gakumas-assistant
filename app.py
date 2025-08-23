import uvicorn
import config

if __name__ == "__main__":
    try:
        uvicorn.run(
            "src.main:app",
            host=config.web_server_host,
            port=config.web_server_port,
            log_level="warning",
            reload=config.auto_reload_server
        )
    except Exception as error:
        print(error)
        input("Press Enter to exit...")