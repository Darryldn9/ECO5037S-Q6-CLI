from algosdk import account, mnemonic, transaction
from algosdk.v2client import algod
import random
import time

# Initialize Algod client
def create_algod_client():
    algod_address = "https://testnet-api.algonode.cloud"
    algod_token = ""
    return algod.AlgodClient(algod_token, algod_address)

# Create a new account
def create_account():
    private_key, address = account.generate_account()
    return private_key, address

# Wait for transaction confirmation
def wait_for_confirmation(client, txid):
    last_round = client.status().get('last-round')
    txinfo = client.pending_transaction_info(txid)
    while not (txinfo.get('confirmed-round') and txinfo.get('confirmed-round') > 0):
        print("Waiting for confirmation...")
        last_round += 1
        client.status_after_block(last_round)
        txinfo = client.pending_transaction_info(txid)
    print(f"Transaction {txid} confirmed in round {txinfo.get('confirmed-round')}.")
    return txinfo

# Create and send a transaction
def send_transaction(client, sender, receiver, amount, note, sk):
    params = client.suggested_params()
    unsigned_txn = transaction.PaymentTxn(sender, params, receiver, amount, None, note.encode())
    signed_txn = unsigned_txn.sign(sk)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id)

# Create ASA (UCTZAR)
def create_asa(client, creator, creator_private_key, total):
    params = client.suggested_params()
    txn = transaction.AssetConfigTxn(
        sender=creator,
        sp=params,
        total=total,
        default_frozen=False,
        unit_name="UCTZAR",
        asset_name="UCT South African Rand",
        manager=creator,
        reserve=creator,
        freeze=creator,
        clawback=creator,
        decimals=6)
    stxn = txn.sign(creator_private_key)
    tx_id = client.send_transaction(stxn)
    response = wait_for_confirmation(client, tx_id)
    return response['asset-index']

# Opt-in to ASA
def opt_in_asa(client, address, private_key, asset_id):
    params = client.suggested_params()
    txn = transaction.AssetOptInTxn(address, params, asset_id)
    signed_txn = txn.sign(private_key)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id)

# Transfer ASA
def transfer_asa(client, sender, receiver, amount, asset_id, private_key):
    params = client.suggested_params()
    txn = transaction.AssetTransferTxn(sender, params, receiver, amount, asset_id)
    signed_txn = txn.sign(private_key)
    tx_id = client.send_transaction(signed_txn)
    wait_for_confirmation(client, tx_id)

# Liquidity Pool
class LiquidityPool:
    def __init__(self, algo_amount, uctzar_amount):
        self.algo_amount = algo_amount
        self.uctzar_amount = uctzar_amount
        self.lp_tokens = (algo_amount * uctzar_amount) ** 0.5
        self.fees = 0

    def add_liquidity(self, algo_amount, uctzar_amount):
        ratio = min(algo_amount / self.algo_amount, uctzar_amount / self.uctzar_amount)
        minted_tokens = self.lp_tokens * ratio
        self.algo_amount += algo_amount
        self.uctzar_amount += uctzar_amount
        self.lp_tokens += minted_tokens
        return minted_tokens

    def remove_liquidity(self, lp_tokens):
        ratio = lp_tokens / self.lp_tokens
        algo_amount = self.algo_amount * ratio
        uctzar_amount = self.uctzar_amount * ratio
        self.algo_amount -= algo_amount
        self.uctzar_amount -= uctzar_amount
        self.lp_tokens -= lp_tokens
        return algo_amount, uctzar_amount

    def swap_algo_to_uctzar(self, algo_amount):
        fee = algo_amount * 0.003
        algo_amount_with_fee = algo_amount - fee
        uctzar_return = (self.uctzar_amount * algo_amount_with_fee) / (self.algo_amount + algo_amount_with_fee)
        self.algo_amount += algo_amount
        self.uctzar_amount -= uctzar_return
        self.fees += fee
        return uctzar_return

    def swap_uctzar_to_algo(self, uctzar_amount):
        fee = uctzar_amount * 0.003
        uctzar_amount_with_fee = uctzar_amount - fee
        algo_return = (self.algo_amount * uctzar_amount_with_fee) / (self.uctzar_amount + uctzar_amount_with_fee)
        self.uctzar_amount += uctzar_amount
        self.algo_amount -= algo_return
        self.fees += fee
        return algo_return

# Main function to simulate the DEX
def main():
    client = create_algod_client()

    # Create accounts
    creator_private_key, creator_address = create_account()
    lp1_private_key, lp1_address = create_account()
    lp2_private_key, lp2_address = create_account()
    trader1_private_key, trader1_address = create_account()
    trader2_private_key, trader2_address = create_account()

    print("Accounts created:")
    print(f"Creator: {creator_address}")
    print(f"LP1: {lp1_address}")
    print(f"LP2: {lp2_address}")
    print(f"Trader1: {trader1_address}")
    print(f"Trader2: {trader2_address}")

    # Fund the creator account using the testnet dispenser
    print(f"\nPlease fund the creator account ({creator_address}) using the Algorand testnet dispenser:")
    print("https://bank.testnet.algorand.network/")
    input("Press Enter once you've funded the account...")

    # Check the balance of the creator account
    account_info = client.account_info(creator_address)
    creator_balance = account_info.get('amount')
    print(f"\nCreator account balance: {creator_balance} microALGOs")

    if creator_balance < 5000000:  # Ensure the creator has at least 5 ALGOs
        print("Insufficient funds in creator account. Please add more ALGOs and try again.")
        return

    # Fund accounts
    send_transaction(client, creator_address, lp1_address, 1000000, "Funding LP1", creator_private_key)
    send_transaction(client, creator_address, lp2_address, 1000000, "Funding LP2", creator_private_key)
    send_transaction(client, creator_address, trader1_address, 1000000, "Funding Trader1", creator_private_key)
    send_transaction(client, creator_address, trader2_address, 1000000, "Funding Trader2", creator_private_key)

    # Create UCTZAR ASA
    uctzar_id = create_asa(client, creator_address, creator_private_key, 1000000000)
    print(f"UCTZAR ASA created with ID: {uctzar_id}")

    # Opt-in to UCTZAR
    opt_in_asa(client, lp1_address, lp1_private_key, uctzar_id)
    opt_in_asa(client, lp2_address, lp2_private_key, uctzar_id)
    opt_in_asa(client, trader1_address, trader1_private_key, uctzar_id)
    opt_in_asa(client, trader2_address, trader2_private_key, uctzar_id)

    # Transfer initial UCTZAR to LPs and traders
    transfer_asa(client, creator_address, lp1_address, 1000000, uctzar_id, creator_private_key)
    transfer_asa(client, creator_address, lp2_address, 1000000, uctzar_id, creator_private_key)
    transfer_asa(client, creator_address, trader1_address, 1000000, uctzar_id, creator_private_key)
    transfer_asa(client, creator_address, trader2_address, 1000000, uctzar_id, creator_private_key)

    # Create liquidity pool
    pool = LiquidityPool(1000000, 2000000)  # 1 ALGO = 2 UCTZAR
    print("Liquidity pool created")

    # LPs provide liquidity
    lp1_tokens = pool.add_liquidity(500000, 1000000)
    lp2_tokens = pool.add_liquidity(500000, 1000000)
    print(f"LP1 received {lp1_tokens} LP tokens")
    print(f"LP2 received {lp2_tokens} LP tokens")

    # Traders swap tokens
    uctzar_received = pool.swap_algo_to_uctzar(100000)
    print(f"Trader1 swapped 100000 microALGOs for {uctzar_received} microUCTZAR")

    algo_received = pool.swap_uctzar_to_algo(200000)
    print(f"Trader2 swapped 200000 microUCTZAR for {algo_received} microALGOs")

    # Distribute fees to LPs
    total_lp_tokens = lp1_tokens + lp2_tokens
    lp1_fee_share = pool.fees * (lp1_tokens / total_lp_tokens)
    lp2_fee_share = pool.fees * (lp2_tokens / total_lp_tokens)
    print(f"LP1 received {lp1_fee_share} microALGOs in fees")
    print(f"LP2 received {lp2_fee_share} microALGOs in fees")

    # LPs withdraw liquidity
    lp1_algo, lp1_uctzar = pool.remove_liquidity(lp1_tokens)
    lp2_algo, lp2_uctzar = pool.remove_liquidity(lp2_tokens)
    print(f"LP1 withdrew {lp1_algo} microALGOs and {lp1_uctzar} microUCTZAR")
    print(f"LP2 withdrew {lp2_algo} microALGOs and {lp2_uctzar} microUCTZAR")

    print("Final pool state:")
    print(f"ALGO: {pool.algo_amount}")
    print(f"UCTZAR: {pool.uctzar_amount}")
    print(f"LP tokens: {pool.lp_tokens}")

if __name__ == "__main__":
    main()

