#!/bin/bash

FRONIUS_IP="192.168.1.142"
STORAGE_API="http://${FRONIUS_IP}/solar_api/v1/GetStorageRealtimeData.cgi"
POWERFLOW_API="http://${FRONIUS_IP}/solar_api/v1/GetPowerFlowRealtimeData.fcgi"

# Colors
GREEN="\033[0;32m"; RED="\033[0;31m"; YELLOW="\033[1;33m"
CYAN="\033[0;36m"; BLUE="\033[0;34m"; MAGENTA="\033[0;35m"; RESET="\033[0m"; BOLD="\033[1m"

extract_json() {
  awk '{if(!s){p=index($0,"{");if(p){s=1;print substr($0,p)}} else print}'
}

# Scale power for display W → kW
scale_power() {
  awk -v v="${1:-0}" 'BEGIN {if(v>=1000||v<=-1000) printf "%.2f kW",v/1000; else printf "%.0f W",v}'
}

while true; do
  # Fetch data
  storage=$(curl -s --max-time 5 "$STORAGE_API" | extract_json)
  flow=$(curl -s --max-time 5 "$POWERFLOW_API" | extract_json)

  # Battery
  soc=$(echo "$storage" | jq -r '.Body.Data | to_entries[0].value.Controller.StateOfCharge_Relative // 0')
  temp=$(echo "$storage" | jq -r '.Body.Data | to_entries[0].value.Controller.Temperature_Cell // 0')

  # Power flow
  p_pv=$(echo "$flow" | jq -r '.Body.Data.Site.P_PV // 0')
  p_load=$(echo "$flow" | jq -r '.Body.Data.Site.P_Load // 0')
  p_grid=$(echo "$flow" | jq -r '.Body.Data.Site.P_Grid // 0')
  p_batt=$(echo "$flow" | jq -r '.Body.Data.Site.P_Akku // 0')
  self_use=$(echo "$flow" | jq -r '.Body.Data.Site.rel_SelfConsumption // 0')

  # Float-safe rounding
  soc=$(awk -v v="$soc" 'BEGIN{printf "%.1f", v}')
  temp=$(awk -v v="$temp" 'BEGIN{printf "%.1f", v}')
  p_pv=$(awk -v v="$p_pv" 'BEGIN{printf "%.0f", v}')
  p_load=$(awk -v v="$p_load" 'BEGIN{printf "%.0f", v}')
  p_grid=$(awk -v v="$p_grid" 'BEGIN{printf "%.0f", v}')
  p_batt=$(awk -v v="$p_batt" 'BEGIN{printf "%.0f", v}')
  self_use=$(awk -v v="$self_use" 'BEGIN{printf "%.1f", v}')
  
  # PV status
  PV_STATE=$(awk -v v="$p_pv" 'BEGIN{if(v<0) print "No Sun"; else print "Production"}')
  # Home status
  LOAD_STATE=$(awk -v v="$p_load" 'BEGIN{if(v<0) print "Usage"; else print "Error"}')

  # Battery status
    BATT_STATE=$(awk -v v="$p_batt" 'BEGIN{
      if(v < 0) print "Charging";
      else if(v > 0) print "Discharging";
      else print "Idle"
    }')

  # Grid status
  GRID_STATE=$(awk -v v="$p_grid" 'BEGIN{if(v<0) print "Exporting"; else print "Importing"}')

  # Clear screen
  clear
  echo -e "${BOLD}⚡ Fronius Energy Dashboard${RESET}"
  echo "================================================"
  echo -e "🔋 Battery: ${GREEN}${soc}%${RESET}   🌡️  ${BLUE}${temp} °C${RESET} (${MAGENTA}${BATT_STATE}${RESET})"
  echo ""
  echo -e "☀️  PV        : ${YELLOW}$(scale_power "$p_pv")${RESET} (${BOLD}${PV_STATE}${RESET})"
  echo -e "🏠 Load      : ${CYAN}$(scale_power "$p_load")${RESET} (${BOLD}${LOAD_STATE}${RESET})"
  echo -e "🔌 Grid      : ${RED}$(scale_power "$p_grid")${RESET} (${BOLD}${GRID_STATE}${RESET})"
  echo -e "🔋 Battery   : ${MAGENTA}$(scale_power "$p_batt")${RESET} (${BOLD}${BATT_STATE}${RESET})"
  echo ""
  echo -e "♻️  Self-consumption: ${GREEN}${self_use}%${RESET}"

  sleep 5
done
