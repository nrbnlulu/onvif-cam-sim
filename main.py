import argparse

from onvif_cam_sim.app import main as run_app


def main() -> None:
    parser = argparse.ArgumentParser(description="Simulated ONVIF camera with multi-stream RTSP")
    parser.add_argument("--config", default="config.yaml", help="Path to config YAML")
    args = parser.parse_args()
    run_app(args.config)


if __name__ == "__main__":
    main()
