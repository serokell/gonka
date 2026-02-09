#!/bin/sh
set -e
set -x

filter_cw20_code() {
  input=$(cat)
  # Remove cw20_code field and its value using sed
  echo "$input" | sed -n -E '
    # If we find cw20_code, skip until the next closing brace
    /[[:space:]]*"cw20_code":[[:space:]]*"/ {
      :skip
      n
      /^[[:space:]]*}[,}]?$/! b skip
      n
    }
    # Print all other lines
    p
  '
}

if [ -z "$KEYRING_BACKEND" ]; then
  echo "KEYRING_BACKEND is not specified defaulting to test"
  KEYRING_BACKEND="test"
fi

# Display the parsed values (for debugging)
echo "Using the following arguments"
echo "KEYRING_BACKEND: $KEYRING_BACKEND"

KEY_NAME="genesis"
APP_NAME="inferenced"
CHAIN_ID="gonka-mainnet"
COIN_DENOM="ngonka"
STATE_DIR="/root/.inference"

NUM_PARTICIPANTS=${NUM_PARTICIPANTS:-1}
NUM_USERS=${NUM_USERS:-0}
SHARED_DIR="${SHARED_DIR:-/shared}"

# Export all keys for a participant to a shared directory
# Usage: export_participant_keys <cold_key_name> <warm_key_name> <temp_home> <output_dir>
export_participant_keys() {
  local cold_name="$1"
  local warm_name="$2"
  local temp_home="$3"
  local out_dir="$4"
  mkdir -p "$out_dir"
  # Account keys (secp256k1): cold + warm private keys and addresses
  $APP_NAME keys export "$cold_name" --unsafe --unarmored-hex --yes \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/cold.hex"
  $APP_NAME keys show "$cold_name" --address \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/cold_address.txt"
  $APP_NAME keys export "$warm_name" --unsafe --unarmored-hex --yes \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/warm.hex"
  $APP_NAME keys show "$warm_name" --address \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/warm_address.txt"
  # Validator + P2P keys (Ed25519)
  cp "$temp_home/config/priv_validator_key.json" "$out_dir/priv_validator_key.json"
  cp "$temp_home/config/node_key.json" "$out_dir/node_key.json"
}

# Export a user account key to a shared directory
# Usage: export_user_key <key_name> <output_dir>
export_user_key() {
  local key_name="$1"
  local out_dir="$2"
  mkdir -p "$out_dir"
  $APP_NAME keys export "$key_name" --unsafe --unarmored-hex --yes \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/key.hex"
  $APP_NAME keys show "$key_name" --address \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" > "$out_dir/address.txt"
}

update_configs() {
  if [ "${REST_API_ACTIVE:-}" = true ]; then
    "$APP_NAME" patch-toml "$STATE_DIR/config/app.toml" app_overrides.toml
  else
    echo "Skipping update node config"
  fi
}


# Init the chain:
# I'm using prod-sim as the chain name (production simulation)
#   and icoin (intelligence coin) as the default denomination
#   and my-node as a node moniker (it doesn't have to be unique)
output=$($APP_NAME init \
  --chain-id "$CHAIN_ID" \
  --default-denom $COIN_DENOM \
  my-node 2>&1)
exit_code=$?
if [ $exit_code -ne 0 ]; then
    echo "Error: '$APP_NAME init' failed with exit code $exit_code"
    echo "Output:"
    echo "$output"
    exit $exit_code
fi
echo "$output" | filter_cw20_code

echo "Setting the chain configuration"

SNAPSHOT_INTERVAL=${SNAPSHOT_INTERVAL:-10}
SNAPSHOT_KEEP_RECENT=${SNAPSHOT_KEEP_RECENT:-5}

$APP_NAME config set client chain-id $CHAIN_ID
$APP_NAME config set client keyring-backend $KEYRING_BACKEND
$APP_NAME config set app minimum-gas-prices "0$COIN_DENOM"
$APP_NAME config set app state-sync.snapshot-interval $SNAPSHOT_INTERVAL
$APP_NAME config set app state-sync.snapshot-keep-recent $SNAPSHOT_KEEP_RECENT

echo "Setting the node configuration (config.toml)"
if [ -n "$P2P_EXTERNAL_ADDRESS" ]; then
  echo "Setting the external address for P2P to $P2P_EXTERNAL_ADDRESS"
  $APP_NAME config set config p2p.external_address "$P2P_EXTERNAL_ADDRESS" --skip-validate
else
  echo "P2P_EXTERNAL_ADDRESS is not set, skipping"
fi

sed -Ei 's/^laddr = ".*:26657"$/laddr = "tcp:\/\/0\.0\.0\.0:26657"/g' \
  $STATE_DIR/config/config.toml
# no seeds for genesis node
sed -Ei "s/^seeds = .*$/seeds = \"\"/g" \
  $STATE_DIR/config/config.toml
#sed -Ei 's/^log_level = "info"$/log_level = "debug"/g' $STATE_DIR/config/config.toml
#if [ -n "${DEBUG-}" ]; then
#  sed -i 's/^log_level = "info"/log_level = "debug"/' "$STATE_DIR/config/config.toml"
#fi


# Create a participant: keys, genesis account, gentx, and optionally export to shared volume
# Usage: create_participant <name> <url> [export: true|false]
create_participant() {
  local p_name="$1"
  local p_url="$2"
  local do_export="${3:-false}"
  local p_warm="${p_name}_warm"
  local p_home

  echo "Creating participant $p_name"

  # Create cold + warm keys
  $APP_NAME keys --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" add "$p_name"
  $APP_NAME keys --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" add "$p_warm"

  # Fund account
  $APP_NAME genesis add-genesis-account "$p_name" "$PARTICIPANT_BALANCE" --keyring-backend $KEYRING_BACKEND

  # Validator key: use STATE_DIR if available (genesis node), otherwise generate in temp home
  if [ "$do_export" = "true" ]; then
    p_home="/tmp/$p_name"
    $APP_NAME init --chain-id "$CHAIN_ID" --default-denom "$COIN_DENOM" "$p_name" --home "$p_home" > /dev/null 2>&1
  else
    p_home="$STATE_DIR"
  fi

  local p_consensus_key
  p_consensus_key=$(jq -r '.pub_key.value' "$p_home/config/priv_validator_key.json")

  # Get warm address
  local p_warm_addr
  p_warm_addr=$($APP_NAME keys show "$p_warm" --address --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR")

  # Run gentx
  $APP_NAME genesis gentx "$p_name" "1$MILLION_BASE" --chain-id "$CHAIN_ID" \
    --pubkey "$p_consensus_key" \
    --node-id "$p_name" \
    --moniker "$p_name" \
    --url "$p_url" \
    --ml-operational-address "$p_warm_addr" \
    || {
    echo "Failed to create gentx for $p_name"
    tail -f /dev/null
  }

  # Export keys to shared volume
  if [ "$do_export" = "true" ]; then
    export_participant_keys "$p_name" "$p_warm" "$p_home" "$SHARED_DIR/$p_name"
  fi
}

echo "Creating POOL key"
$APP_NAME keys \
    --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" \
    add "POOL_product_science_inc"

modify_genesis_file() {
  local json_file="$HOME/.inference/config/genesis.json"
  local override_file="$1"


  if [ ! -f "$override_file" ]; then
    echo "Override file $override_file does not exist. Exiting..."
    return
  fi
  echo "Checking if jq is installed"
  which jq
  jq ". * input" "$json_file" "$override_file" > "${json_file}.tmp"
  mv "${json_file}.tmp" "$json_file"
  echo "Modified $json_file with file: $override_file"
  cat "$json_file" | filter_cw20_code
}

# Usage
modify_genesis_file 'denom.json'
MILLION_BASE="000000$COIN_DENOM"
NATIVE="000000000$COIN_DENOM"
MILLION_NATIVE="000000$NATIVE"

PARTICIPANT_BALANCE="${PARTICIPANT_BALANCE:-2${NATIVE}}"
USER_BALANCE="${USER_BALANCE:-100${MILLION_NATIVE}}"

$APP_NAME genesis add-genesis-account "POOL_product_science_inc" "160$MILLION_NATIVE" --keyring-backend $KEYRING_BACKEND

URL_VALUE="${PUBLIC_URL:-http://localhost:9000}"

# Genesis node (participant-0, runs locally — no key export needed)
create_participant "$KEY_NAME" "$URL_VALUE"

# Additional participants (export keys to shared volume for their nodes)
for i in $(seq 1 $((NUM_PARTICIPANTS - 1))); do
  create_participant "participant-$i" "http://participant-${i}-api:9000" "true"
done

# Create user accounts
if [ "$NUM_USERS" -gt 0 ]; then
  for i in $(seq 0 $((NUM_USERS - 1))); do
    U_NAME="user-$i"
    echo "Creating user $U_NAME"
    $APP_NAME keys --keyring-backend $KEYRING_BACKEND --keyring-dir "$STATE_DIR" add "$U_NAME"
    $APP_NAME genesis add-genesis-account "$U_NAME" "$USER_BALANCE" --keyring-backend $KEYRING_BACKEND
    export_user_key "$U_NAME" "$SHARED_DIR/$U_NAME"
  done
fi

# Collect all gentxs and patch genesis
output=$($APP_NAME genesis collect-gentxs 2>&1)
echo "$output" | filter_cw20_code

# Patch genesis with genparticipant transactions
echo "Patching genesis with genparticipant transactions"
output=$($APP_NAME genesis patch-genesis 2>&1)
echo "$output" | filter_cw20_code

# tgbot
TG_ACC=gonka1va4hlpg929n6hhg4wc8hl0g9yp4nheqxm6k9wr

if [ "$INIT_TGBOT" = "true" ]; then
  echo "Adding the tgbot account"
  $APP_NAME genesis add-genesis-account $TG_ACC "100$MILLION_NATIVE" --keyring-backend $KEYRING_BACKEND
fi

modify_genesis_file 'genesis_overrides.json'
modify_genesis_file "$HOME/.inference/genesis_overrides.json"
echo "Genesis file created"
echo "Setting up overrides for config.toml"
 # Process CONFIG_ environment variables
 for var in $(env | grep '^CONFIG_'); do
    # Extract key and value
    key=${var%%=*}
    value=${var#*=}

    # Remove CONFIG_ prefix and transform __ to .
    config_key=${key#CONFIG_}
    config_key=${config_key//__/.}

    echo "Setting config: $config_key = $value"
    $APP_NAME config set config "$config_key" "$value" --skip-validate
 done
# Check and apply config overrides if present
if [ -f "config_override.toml" ]; then
    echo "Applying config overrides from config_override.toml"
    $APP_NAME patch-toml "$STATE_DIR/config/config.toml" config_override.toml
fi

update_configs

echo "Init for cosmovisor"
cosmovisor init /usr/bin/inferenced || {
  echo "Cosmovisor failed, idling the container..."
  tail -f /dev/null
}

echo "Starting cosmovisor and the chain"
#cosmovisor run start || {
#  echo "Cosmovisor failed, idling the container..."
#  tail -f /dev/null
#}

cosmovisor run start &
COSMOVISOR_PID=$!
sleep 20 # wait for the first block

# import private key for tgbot and sign tx to make tgbot public key registered n the network
if [ "$INIT_TGBOT" = "true" ]; then
    echo "Initializing tgbot account..."

    if [ -z "$TGBOT_PRIVATE_KEY_PASS" ]; then
        echo "Error: TGBOT_PRIVATE_KEY_PASS is empty. Aborting initialization."
        exit 1
    fi

    echo "$TGBOT_PRIVATE_KEY_PASS" | inferenced keys import tgbot tgbot_private_key.json

    inferenced tx bank send $TG_ACC $TG_ACC 100nicoin --from tgbot --yes
    echo "tgbot account successfully initialized!"
else
    echo "INIT_TGBOT is not set to true. Skipping tgbot initialization."
fi

wait $COSMOVISOR_PID
