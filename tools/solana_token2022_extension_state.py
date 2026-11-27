"""Bounded parsed RPC extension-state observations. No program audit or clearance."""
from cyberbot.solana_pilot import address

# Agave account-decoder-client-types/src/token.rs, UiExtension and Ui* structs.
POINTERS={
    "transferHook":("authority","programId"),
    "permanentDelegate":("delegate",),
    "metadataPointer":("authority","metadataAddress"),
    "tokenMetadata":("updateAuthority","mint"),
    "mintCloseAuthority":("closeAuthority",),
    "transferFeeConfig":("transferFeeConfigAuthority","withdrawWithheldAuthority"),
    "pausableConfig":("authority",),
    "groupPointer":("authority","groupAddress"),
    "groupMemberPointer":("authority","memberAddress"),
}

def pointer(state,key):
    if key not in state:return {"status":"not_reported"}
    v=state[key]
    if v is None:return {"status":"null"}
    if address(v):return {"status":"present","address":v}
    return {"status":"invalid"}

def bounded_integer(value,maximum):
    if type(value) is int and 0<=value<=maximum:return value
    return None

def fee_schedule(value):
    if not isinstance(value,dict):return None
    epoch=bounded_integer(value.get("epoch"),2**64-1)
    maximum=bounded_integer(value.get("maximumFee"),2**64-1)
    bps=bounded_integer(value.get("transferFeeBasisPoints"),10000)
    if None in (epoch,maximum,bps):return None
    return {"epoch":str(epoch),"maximum_fee_raw":str(maximum),"basis_points":bps}

def observe(entry,mint=None):
    name=entry["extension"]
    result={"extension":name,"state_verified":False,"trade_eligible":False}
    if name=="nonTransferable":
        return dict(result,status="marker_observed")
    if name not in POINTERS and name!="defaultAccountState":
        return dict(result,status="state_decoder_not_implemented")
    state=entry.get("state")
    if not isinstance(state,dict):return dict(result,status="state_missing_or_invalid")
    pointers={key:pointer(state,key) for key in POINTERS.get(name,())}
    result["pointers"]=pointers
    complete=all(v["status"] in ("present","null") for v in pointers.values())
    if name=="transferFeeConfig":
        schedules={key:fee_schedule(state.get(key)) for key in ("olderTransferFee","newerTransferFee")}
        withheld=bounded_integer(state.get("withheldAmount"),2**64-1)
        result["fee_schedules"]=schedules
        result["withheld_raw"]=str(withheld) if withheld is not None else None
        result["active_fee_verified"]=False
        complete=complete and all(v is not None for v in schedules.values()) and withheld is not None
    elif name=="defaultAccountState":
        value=state.get("accountState")
        result["account_state"]=value if value in ("uninitialized","initialized","frozen") else None
        complete=complete and result["account_state"] is not None
    elif name=="pausableConfig":
        value=state.get("paused")
        result["paused"]=value if type(value) is bool else None
        complete=complete and result["paused"] is not None
    elif name=="tokenMetadata":
        value=pointers["mint"]
        result["metadata_mint_matches"]=value.get("address")==mint if mint is not None and value["status"]=="present" else None
        complete=complete and value["status"]=="present" and result["metadata_mint_matches"] is not False
    # Metadata name, URI, symbol and arbitrary payloads are deliberately not retained.
    return dict(result,status="parsed_fields_observed" if complete else "state_missing_or_invalid")
