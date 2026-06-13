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
    env_path = os.path.join(current_dir, ".env")
    
    use_existing = False
    email = ""
    password = ""
    
    if os.path.exists(env_path):
        existing_vars = {}
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith("#"):
                        continue
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        existing_vars[key] = val
        except Exception as e:
            print(f"[WARN] Error reading existing .env file: {e}")

        if existing_vars.get("MOODLE_USERNAME") and existing_vars.get("MOODLE_PASSWORD"):
            print(f"An existing .env file was found with credentials for: {existing_vars['MOODLE_USERNAME']}")
            while True:
                response = input("Do you want to use the already existing .env file? (y/n): ").strip().lower()
                if response in ("y", "yes"):
                    use_existing = True
                    email = existing_vars["MOODLE_USERNAME"]
                    password = existing_vars["MOODLE_PASSWORD"]
                    break
                elif response in ("n", "no"):
                    use_existing = False
                    break
                else:
                    print("Please enter 'y' or 'n'.")
        else:
            print("An existing .env file was found, but it is incomplete or missing credentials.")

    if use_existing:
        print("[OK] Using existing credentials from .env.")
    else:
        email = input("Enter your Moodle/eKursy email (e.g., username@student.put.poznan.pl): ").strip()
        while not email:
            email = input("Email cannot be empty. Please enter your email: ").strip()
            
        password = getpass.getpass("Enter your Moodle/eKursy password (hidden): ").strip()
        while not password:
            password = getpass.getpass("Password cannot be empty. Please enter your password: ").strip()

    # 3. Create .env file in the root directory
    print("\n3. Creating local .env file...")
    if use_existing:
        print("[OK] .env file already exists and is being reused.")
    else:
        try:
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
    config_data["mcpServers"]["ekursy"] = {
        "serverUrl": "http://localhost:6969/mcp"
    }
    
    # Write back config
    try:
        os.makedirs(os.path.dirname(target_path), exist_ok=True)
        with open(target_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2)
        print(f"[OK] Successfully added 'ekursy' to config at {target_path}")
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
