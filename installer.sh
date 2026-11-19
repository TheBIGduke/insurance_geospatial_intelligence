#!/bin/bash
# Author: Kaléin Tamaríz

PACKAGE_NAME="insurance_platform"

# Directories
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" &> /dev/null && pwd )"
VENV_DIR="$SCRIPT_DIR/.venv" # Virtual env named '.venv'
APP_DATA_DIR="$HOME/.${PACKAGE_NAME}"

info()   { printf "\n\033[1;34m[INFO]\033[0m %s\n" "$*"; }
ok()  { printf "\033[1;32m[OK]\033[0m %s\n" "$*"; }
warn()  { printf "\033[1;33m[WARN]\033[0m %s\n" "$*"; }
fail()  { printf "\033[1;31m[FAIL]\033[0m %s\n" "$*"; exit 1; }


APT_PKGS=(
  python3-dev python3-venv postgresql postgis gdal-bin sqlite3 sqlitebrowser curl mkcert libnss3-tools
)

info "SCRIPT_DIR: $SCRIPT_DIR"

# Install pre-requisites
install_apt() {
  info "Updating system and installing packages ..."
  sudo apt update -y
  sudo apt install -y "${APT_PKGS[@]}"
  ok "System packages installed."
}

verify_git_lfs() {
  info "Verifying Git LFS installation..."
  if ! command -v git-lfs >/dev/null 2>&1; then
    warn "git-lfs not found. Installing..."
    # Download and install git-lfs binary (Ubuntu package is often outdated)
    local lfs_version="3.6.0"
    local lfs_url="https://github.com/git-lfs/git-lfs/releases/download/v${lfs_version}/git-lfs-linux-amd64-v${lfs_version}.tar.gz"
    curl -L "$lfs_url" | tar -xz -C /tmp
    sudo mv /tmp/git-lfs-${lfs_version}/git-lfs /usr/local/bin/
    rm -rf /tmp/git-lfs-${lfs_version}
    ok "git-lfs installed to /usr/local/bin/git-lfs"
  else
    ok "git-lfs is already installed."
  fi

  # Initialize git-lfs for this repository (safe to run multiple times)
  git lfs install --local
  ok "Git LFS initialized for this repository"
}

verify_uv_setup() {
    info "Verifying uv installation..."
    source ~/.bashrc
    if [ ! -f "$HOME/.local/bin/uv" ] && ! command -v uv >/dev/null 2>&1; then
        warn "uv not found. Installing uv..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        ok "uv installed."
    else
        ok "uv is already installed."
    fi
}


virtual_env_setup() {
    local clear_venv="${1:-false}"

    if [ -d "$VENV_DIR" ] && [ "$clear_venv" != "true" ]; then
        warn "Virtual environment already exists."
        read -p "Do you want to delete and recreate it? [y/N] " response
        case "$response" in
            [yY][eE][sS]|[yY])
                clear_venv="true"
                ;;
            *)
                info "Using existing virtual environment."
                ;;
        esac
    fi

    # Create a virtual environment, if needed and not already created
    if [ ! -d "$VENV_DIR" ] || [ "$clear_venv" = "true" ]; then
        if [ "$clear_venv" = "true" ]; then
            info "Clearing existing virtual environment..."
            $HOME/.local/bin/uv venv --clear "$VENV_DIR"
        else
            $HOME/.local/bin/uv venv "$VENV_DIR"
        fi
        ok "Virtual environment created."
    fi

    source "$VENV_DIR/bin/activate"

    if [[ ! -f "$SCRIPT_DIR/requirements.txt" ]]; then
        fail "requirements.txt not found in $SCRIPT_DIR"
    fi

    uv pip install -r requirements.txt

    ok "Requirements successfully installed!!!"
}


ssl_cert_setup() {
    info "Setting up local SSL certificates with mkcert..."

    # Install the local CA in the system trust store
    mkcert -install

    # Get local IP address (first one found)
    LOCAL_IP=$(hostname -I | awk '{print $1}')

    if [ -z "$LOCAL_IP" ]; then
        warn "Could not detect local IP address. Falling back to 127.0.0.1"
        LOCAL_IP="127.0.0.1"
    fi

    # Create certs directory
    mkdir -p "$SCRIPT_DIR/certs"

    info "Generating certificate for localhost, 127.0.0.1, and $LOCAL_IP..."
    mkcert -cert-file "$SCRIPT_DIR/certs/cert.pem" -key-file "$SCRIPT_DIR/certs/key.pem" localhost 127.0.0.1 "$LOCAL_IP"

    ok "SSL certificates generated in $SCRIPT_DIR/certs/"
}

extract_data_zip() {
    local data_zip="$SCRIPT_DIR/resources/data.zip"
    local data_dir="$SCRIPT_DIR/data"

    if [ -f "$data_zip" ]; then
        info "Found resources/data.zip — extracting to data/..."
        mkdir -p "$data_dir"
        unzip -o "$data_zip" -d "$data_dir"
        ok "Data files extracted to $data_dir"

        # Extract nested txdot_roads.zip if present
        local roads_zip="$data_dir/txdot_roads.zip"
        if [ -f "$roads_zip" ]; then
            info "Extracting nested txdot_roads.zip..."
            unzip -o "$roads_zip" -d "$data_dir"

            # Create .prj file for EPSG:4326 (shapefile doesn't always include it)
            cat > "$data_dir/txdot_roads.prj" << 'PRJEOF'
GEOGCS["WGS 84",DATUM["WGS_1984",SPHEROID["WGS 84",6378137,298.257223563,AUTHORITY["EPSG","7030"]],AUTHORITY["EPSG","6326"]],PRIMEM["Greenwich",0,AUTHORITY["EPSG","8901"]],UNIT["degree",0.0174532925199433,AUTHORITY["EPSG","9122"]],AUTHORITY["EPSG","4326"]]
PRJEOF
            ok "roadways roads shapefile extracted with CRS"
        fi
    else
        warn "resources/data.zip not found — skipping data extraction."
        info "You can manually place data files in data/ later (see README.md)"
        mkdir -p "$data_dir"
    fi
}

config_from_template_setup() {
    local overwrite_file="${1:-false}"

    mkdir -p "$APP_DATA_DIR/config"

    if [ -f "$APP_DATA_DIR/config/config.yaml" ] && [ "$overwrite_file" != "true" ]; then
        warn "Config file already exists."
        read -p "Do you want to overwrite the config.yaml file? [y/N] " response
        case "$response" in
            [yY][eE][sS]|[yY])
                overwrite_file="true"
                ;;
            *)
                info "Using existing config file."
                ;;
        esac
    fi

    if [ ! -f "$APP_DATA_DIR/config/config.yaml" ] || [ "$overwrite_file" = "true" ]; then
        if [ -f "$APP_DATA_DIR/config/config.yaml" ]; then
            cp "$SCRIPT_DIR/config/config_template.yaml" "$APP_DATA_DIR/config/config.yaml"
            ok "Config file overwritten."
        else
            cp "$SCRIPT_DIR/config/config_template.yaml" "$APP_DATA_DIR/config/config.yaml"
            ok "Config file created."
        fi
    fi
}

pre_commit_setup() {
    info "Setting up pre-commit and validating all files ..."
    pre-commit clean
    pre-commit install
    pre-commit run --all-files
}

post_instructions() {
    info "Installation complete!"
    info "Next steps:"
    info "  1. Ensure PostgreSQL is running and database exists:"
    info "     sudo -u postgres createdb insurance_geospatial_intelligence"
    info "     sudo -u postgres psql -d insurance_geospatial_intelligence -c \"CREATE EXTENSION postgis;\""
    info "  2. Update database credentials in ~/.insurance_platform/config/config.yaml"
    info "  3. Activate virtual environment: source .venv/bin/activate"
    info "  4. Run the pipeline: python run_pipeline.py"
    info "  5. Start the visualization server: python main.py"
    info "  6. Open https://localhost:8080 in your browser"
}


main() {
  local clear_venv=false
  local overwrite_file=false

  # Process command-line arguments
  for arg in "$@"; do
    case $arg in
      --clear|-c)
        clear_venv=true
        shift
        ;;
    esac
    case $arg in
      --overwrite|-o)
        overwrite_file=true
        shift
        ;;
    esac
  done

  install_apt
  verify_git_lfs
  verify_uv_setup
  virtual_env_setup "$clear_venv"
  ssl_cert_setup
  extract_data_zip
  config_from_template_setup "$overwrite_file"
  pre_commit_setup
  post_instructions
}

## Usage ##
# ./installer.sh
# ./installer.sh --clear --overwrite

main "$@"
