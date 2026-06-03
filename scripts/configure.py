import os
import sys
import json
import subprocess
import getpass

def main():
    print("=== eKursy MCP Setup ===")
    
    # Root directory is the parent of this scripts/ directory
    current_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    
    # 1. Update git submodules
    print("\n1. Initializing and updating git submodules...")
    try:
        subprocess.run(["git", "submodule", "update", "--init", "--recursive"], check=True, cwd=current_dir)
        print("[OK] Submodules updated successfully.")
    except Exception as e:
        print(f"[WARN] Warning: Could not update submodules via git: {e}")
        print("Please make sure you have git installed and run 'git submodule update --init --recursive' manually.")
    
    # 2. Ask user for credentials
    print("\n2. Configuring credentials...")
    email = input("Enter your Moodle/eKursy email (e.g., username@student.put.poznan.pl): ").strip()
    while not email:
        email = input("Email cannot be empty. Please enter your email: ").strip()
        
    password = getpass.getpass("Enter your Moodle/eKursy password (hidden): ").strip()
    while not password:
        password = getpass.getpass("Password cannot be empty. Please enter your password: ").strip()

    # 3. Create .env file in the root directory
    print("\n3. Creating local .env file...")
    try:
        env_path = os.path.join(current_dir, ".env")
        with open(env_path, "w", encoding="utf-8") as f:
            f.write(f'MOODLE_USERNAME="{email}"\n')
            f.write(f'MOODLE_PASSWORD="{password}"\n')
        print("[OK] .env file created successfully.")
    except Exception as e:
        print(f"[ERROR] Error writing .env file: {e}")
        sys.exit(1)

    # 4. Configure Gemini / Antigravity
    print("\n4. Adding MCP server to Gemini/Antigravity configuration...")
    gemini_config_dir = os.path.expanduser("~/.gemini/config")
    
    # Check for mcp_config.json first, then config.json in config subdir
    mcp_config_path = os.path.join(gemini_config_dir, "mcp_config.json")
    config_path = os.path.join(gemini_config_dir, "config.json")
    
    target_path = None
    if os.path.exists(mcp_config_path):
        target_path = mcp_config_path
    elif os.path.exists(config_path):
        target_path = config_path
    else:
        # If neither exists, default to mcp_config.json in the config directory
        target_path = mcp_config_path
        
    print(f"Target config file: {target_path}")
    
    # Read existing config
    config_data = {}
    if os.path.exists(target_path):
        try:
            with open(target_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                if content:
                    config_data = json.loads(content)
        except Exception as e:
            print(f"[WARN] Warning: Could not read existing config file: {e}")
            
    if "mcpServers" not in config_data:
        config_data["mcpServers"] = {}
        
    # Configure the MCP server definition
    config_data["mcpServers"]["ekursy-mcp"] = {
        "serverUrl": "http://localhost:6969/mcp"
    }
    
    # Write back config
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        print(f"[OK] Successfully added 'ekursy-mcp' to config at {target_path}")
    except Exception as e:
        print(f"[ERROR] Error updating Gemini config: {e}")
        print("Please add the config manually as detailed in the README.")
        
    # 5. Build and start services via Docker Compose
    print("\n5. Starting Docker services...")
    docker_available = True
    try:
        subprocess.run(["docker", "compose", "up", "--build", "-d"], check=True, cwd=current_dir)
        print("[OK] Docker services built and started successfully in the background.")
    except FileNotFoundError:
        print("[WARN] Warning: Docker command was not found. Please ensure Docker is installed and in your PATH.")
        docker_available = False
    except subprocess.CalledProcessError as e:
        print(f"[WARN] Warning: Docker Compose failed with exit status {e.returncode}. Please ensure the Docker daemon is running.")
        docker_available = False
    except Exception as e:
        print(f"[WARN] Warning: An unexpected error occurred while starting Docker services: {e}")
        docker_available = False

    print("\n=== Setup Completed Successfully ===")
    if docker_available:
        print("Both services are running in the background. You can check logs using: docker compose logs -f")
    else:
        print("To run the services manually, start Docker Desktop and run: docker compose up --build -d")
    
    print("You must restart Antigravity to see the effects.")
    print("Verify in Settings -> Customization under Installed MCP Servers if MCP server is installed and runs correctly ")

if __name__ == "__main__":
    main()
