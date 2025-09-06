# Tele Bot Trading
Tele Bot Trading is a Python-based signal bot designed to provide trading signals for Binance Futures. It leverages real-time K-line data from Binance's WebSocket API and a custom strategy based on RSI and Moving Average indicators to generate actionable insights. The signals are sent directly to a Telegram channel, complete with detailed price levels, leverage information, and a chart image.

## Features
 - **Signal Generation**: Listens to Binance WebSocket streams for multiple symbols and timeframes (15m, 30m, 1h, 4h).
 - **Risk Management**: Filters symbols by market capitalization using the CoinGecko API and includes recommended leverage and margin type in the signal message.
 - **Telegram Integration**: Delivers formatted signal messages to a Telegram channel.
 - **Chart Generation**: Creates visual candlestick charts with signal-specific entry points, take-profit (TP) levels, and stop-loss (SL) levels.
 - **Performance**: Uses a dedicated background thread for chart rendering with Playwright for improved efficiency and resource management.
 - **Simulation Mode**: Includes a simulation mode to lower the signal cooldown and minimum klines requirement for development and validation purposes.
 - **Containerized**: Optimized for deployment in a Docker container. 

## Getting Started
### Prerequisites
 - Python 3.10 or higher
 - A Telegram bot token and chat ID
 - A Binance API key and API secret for a Futures account
 - Docker (for containerized deployment) 
 - VPN (optional, if deployed on geo-restricted location)
### Installation
1. Clone the repository to your local machine: 
    ```
    git clone https://github.com/your-username/tele-bot-trading.git
    cd tele-bot-trading`
    ```

2. Create and activate a virtual environment (optional but recommended): 
    ```
    python -m venv venv
    source venv/bin/activate
    ```
3. Install the required Python libraries: 
    ```
    pip install -r requirements.txt
    ```


### Configuration
- Copy the `.env.example` file to `.env` and fill in your credentials and preferences.
    ```
    cp .env.example .env
    ```
- Edit the .env file as per your need

### Usage
#### Run with Docker (Recommended)
1. Build the Docker image from the project root:
   `docker build -t tele-bot-trading .`

2. Run the container, passing your environment variables from the .env file and mapping a volume for persistent chart storage:
    ```
    docker run -d --name tele-bot-trading-bot --env-file .env -v $(pwd)/charts:/app/charts tele-bot-trading`
    ```
   If in **Windows Powershell**, you should probably change the `$(pwd)` to `${PWD}`.


3. To stop the bot, run:
    ```
    docker stop tele-bot-trading-bot
    ```

#### Run Locally
Run the main.py script from your terminal.
`python main.py`

### Important Considerations
#### Binance Geo-Restrictions and VPN Usage
Due to regulatory restrictions, Binance services are not available in all countries.
Attempting to access Binance from a restricted location, even with an API key, can lead to your account being frozen or suspended. 
If you are located in a region where Binance is blocked, you must use a VPN.

**Cautionary List**:
 - Absolute Ban: Countries like Algeria, Bangladesh, China, Egypt, Iraq, Morocco, Nepal, Qatar, and Tunisia have strict cryptocurrency regulations that could prevent Binance access.
 - Implicit Ban/Restrictions: Many other countries, including the United States, United Kingdom, Canada, and several European nations, have complex regulations or regional restrictions.
 - Always check the official Binance website for the most up-to-date information on service availability in your area. 

**Best Practice for VPN Use with Binance**:
 - Use a reliable VPN provider.
 - Connect to a server in a supported country where you have a verified account.
 - Do not switch VPN locations while trading, as this can trigger security alerts and cause your account to be locked.
 - Avoid locations with known issues. For instance, accessing Binance International from the US is a known cause of account suspension.
 - Use the API from a static IP address. Some VPNs offer static IP addresses, which is preferable to dynamic ones.