#!/bin/bash
#
# Koda Installation Script
# Automatically detects OS and installs all dependencies
#

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print functions
print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_step() {
    echo -e "${GREEN}▶${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

print_error() {
    echo -e "${RED}✖${NC} $1"
}

print_success() {
    echo -e "${GREEN}✔${NC} $1"
}

# Detect OS
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
        if [[ $(uname -m) == "arm64" ]]; then
            ARCH="arm64"
        else
            ARCH="x86_64"
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
        # Detect distribution
        if [ -f /etc/os-release ]; then
            . /etc/os-release
            DISTRO=$ID
            DISTRO_VERSION=$VERSION_ID
        elif [ -f /etc/debian_version ]; then
            DISTRO="debian"
        elif [ -f /etc/redhat-release ]; then
            DISTRO="rhel"
        else
            DISTRO="unknown"
        fi
    else
        print_error "Unsupported OS: $OSTYPE"
        exit 1
    fi
}

# Check if command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Install Homebrew (macOS)
install_homebrew() {
    if ! command_exists brew; then
        print_step "Installing Homebrew..."
        /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
        
        # Add Homebrew to PATH for Apple Silicon
        if [[ "$ARCH" == "arm64" ]]; then
            echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
            eval "$(/opt/homebrew/bin/brew shellenv)"
        fi
        print_success "Homebrew installed"
    else
        print_success "Homebrew already installed"
    fi
}

# Install Python (macOS)
install_python_macos() {
    if ! command_exists python3.12 && ! command_exists python3.11; then
        print_step "Installing Python 3.12..."
        brew install python@3.12
        print_success "Python 3.12 installed"
    else
        print_success "Python 3.11+ already installed"
    fi
}

# Install Python (Linux)
install_python_linux() {
    if ! command_exists python3.12 && ! command_exists python3.11; then
        print_step "Installing Python..."
        case $DISTRO in
            ubuntu|debian|pop)
                sudo apt-get update
                sudo apt-get install -y python3.12 python3.12-venv python3-pip || \
                sudo apt-get install -y python3.11 python3.11-venv python3-pip || \
                sudo apt-get install -y python3 python3-venv python3-pip
                ;;
            fedora)
                sudo dnf install -y python3.12 python3-pip || \
                sudo dnf install -y python3.11 python3-pip || \
                sudo dnf install -y python3 python3-pip
                ;;
            centos|rhel|rocky|alma)
                sudo yum install -y python3.12 python3-pip || \
                sudo yum install -y python3.11 python3-pip || \
                sudo yum install -y python3 python3-pip
                ;;
            arch|manjaro)
                sudo pacman -S --noconfirm python python-pip
                ;;
            opensuse*)
                sudo zypper install -y python312 python312-pip || \
                sudo zypper install -y python311 python311-pip || \
                sudo zypper install -y python3 python3-pip
                ;;
            *)
                print_warning "Unknown distribution. Please install Python 3.11+ manually."
                ;;
        esac
        print_success "Python installed"
    else
        print_success "Python 3.11+ already installed"
    fi
}

# Install Node.js (macOS)
install_nodejs_macos() {
    if ! command_exists node; then
        print_step "Installing Node.js 20 (required for WhatsApp)..."
        brew install node@20
        brew link node@20
        print_success "Node.js installed"
    else
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VERSION" -lt 18 ]; then
            print_step "Upgrading Node.js to v20..."
            brew install node@20
            brew link --overwrite node@20
            print_success "Node.js upgraded"
        else
            print_success "Node.js $(node -v) already installed"
        fi
    fi
}

# Install Node.js (Linux)
install_nodejs_linux() {
    if ! command_exists node; then
        print_step "Installing Node.js 20 (required for WhatsApp)..."
        case $DISTRO in
            ubuntu|debian|pop)
                curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash -
                sudo apt-get install -y nodejs
                ;;
            fedora)
                sudo dnf install -y nodejs npm || {
                    curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
                    sudo dnf install -y nodejs
                }
                ;;
            centos|rhel|rocky|alma)
                curl -fsSL https://rpm.nodesource.com/setup_20.x | sudo bash -
                sudo yum install -y nodejs
                ;;
            arch|manjaro)
                sudo pacman -S --noconfirm nodejs npm
                ;;
            opensuse*)
                sudo zypper install -y nodejs20 npm20 || sudo zypper install -y nodejs npm
                ;;
            *)
                print_warning "Unknown distribution. Please install Node.js 20+ manually."
                ;;
        esac
        print_success "Node.js installed"
    else
        NODE_VERSION=$(node -v | cut -d'v' -f2 | cut -d'.' -f1)
        if [ "$NODE_VERSION" -lt 18 ]; then
            print_warning "Node.js version is < 18. WhatsApp bridge may not work."
            print_warning "Please upgrade Node.js to v20 manually."
        else
            print_success "Node.js $(node -v) already installed"
        fi
    fi
}

# Install uv (fast Python package manager)
install_uv() {
    if ! command_exists uv; then
        print_step "Installing uv (fast Python package manager)..."
        curl -LsSf https://astral.sh/uv/install.sh | sh
        
        # Add to PATH
        export PATH="$HOME/.cargo/bin:$PATH"
        
        # Add to shell profile
        if [[ -f ~/.bashrc ]]; then
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.bashrc
        fi
        if [[ -f ~/.zshrc ]]; then
            echo 'export PATH="$HOME/.cargo/bin:$PATH"' >> ~/.zshrc
        fi
        
        print_success "uv installed"
    else
        print_success "uv already installed"
    fi
}

# Install git if not present
install_git() {
    if ! command_exists git; then
        print_step "Installing git..."
        if [[ "$OS" == "macos" ]]; then
            brew install git
        else
            case $DISTRO in
                ubuntu|debian|pop)
                    sudo apt-get install -y git
                    ;;
                fedora)
                    sudo dnf install -y git
                    ;;
                centos|rhel|rocky|alma)
                    sudo yum install -y git
                    ;;
                arch|manjaro)
                    sudo pacman -S --noconfirm git
                    ;;
                opensuse*)
                    sudo zypper install -y git
                    ;;
            esac
        fi
        print_success "git installed"
    else
        print_success "git already installed"
    fi
}

# Setup Koda
setup_koda() {
    print_step "Setting up Koda..."
    
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    
    # Check if we're in the Koda directory
    if [[ -f "$SCRIPT_DIR/pyproject.toml" ]]; then
        cd "$SCRIPT_DIR"
    elif [[ -d "$HOME/koda" ]]; then
        cd "$HOME/koda"
    else
        print_error "Could not find Koda directory. Please run this script from the Koda folder."
        exit 1
    fi
    
    # Create virtual environment
    print_step "Creating virtual environment..."
    if command_exists python3.12; then
        PYTHON_CMD="python3.12"
    elif command_exists python3.11; then
        PYTHON_CMD="python3.11"
    else
        PYTHON_CMD="python3"
    fi
    
    if command_exists uv; then
        uv venv --python $PYTHON_CMD .venv
    else
        $PYTHON_CMD -m venv .venv
    fi
    print_success "Virtual environment created"
    
    # Activate virtual environment
    source .venv/bin/activate
    
    # Install Koda with all optional dependencies
    print_step "Installing Koda and dependencies..."
    if command_exists uv; then
        uv pip install -e ".[web,linkedin]"
    else
        pip install --upgrade pip
        pip install -e ".[web,linkedin]"
    fi
    print_success "Koda installed"
    
    # Build WhatsApp bridge
    if [[ -d "bridge" ]]; then
        print_step "Building WhatsApp bridge..."
        cd bridge
        npm install
        npm run build
        cd ..
        print_success "WhatsApp bridge built"
    fi
    
    # Create config directory
    mkdir -p ~/.koda
    print_success "Config directory created at ~/.koda"
}

# Main installation
main() {
    print_header "🐕 Koda Installation Script"
    
    echo -e "This script will install all dependencies for Koda.\n"
    
    # Detect OS
    detect_os
    echo -e "Detected OS: ${GREEN}$OS${NC}"
    if [[ "$OS" == "linux" ]]; then
        echo -e "Distribution: ${GREEN}$DISTRO${NC}"
    fi
    if [[ "$OS" == "macos" ]]; then
        echo -e "Architecture: ${GREEN}$ARCH${NC}"
    fi
    echo ""
    
    # Confirm installation
    read -p "Continue with installation? [Y/n] " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]] && [[ ! -z $REPLY ]]; then
        echo "Installation cancelled."
        exit 0
    fi
    
    print_header "Installing System Dependencies"
    
    # Install dependencies based on OS
    if [[ "$OS" == "macos" ]]; then
        install_homebrew
        install_python_macos
        install_nodejs_macos
    else
        install_git
        install_python_linux
        install_nodejs_linux
    fi
    
    install_uv
    
    print_header "Setting Up Koda"
    
    setup_koda
    
    print_header "🎉 Installation Complete!"
    
    echo -e "Koda has been installed successfully!\n"
    echo -e "Next steps:"
    echo -e "  ${GREEN}1.${NC} Activate the virtual environment:"
    echo -e "     ${YELLOW}source .venv/bin/activate${NC}\n"
    echo -e "  ${GREEN}2.${NC} Run the setup wizard:"
    echo -e "     ${YELLOW}koda onboard${NC}\n"
    echo -e "  ${GREEN}3.${NC} Start chatting:"
    echo -e "     ${YELLOW}koda agent -m \"Hello!\"${NC}\n"
    echo -e "  ${GREEN}4.${NC} For WhatsApp, start the gateway (QR login starts automatically):"
    echo -e "     ${YELLOW}koda gateway${NC}\n"
    echo -e "Documentation: ${BLUE}https://github.com/ronaldjonkers/Koda${NC}"
}

# Run main
main "$@"
