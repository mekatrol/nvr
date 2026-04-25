from nvr_web.server import NvrWebServer


def main() -> None:
    server = NvrWebServer()
    print(
        f"NVR web server listening on http://{server.host}:{server.port}/",
        flush=True,
    )
    print("NVR web UI ready at http://127.0.0.1:5173/", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
