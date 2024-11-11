from algosdk import account, mnemonic
from algosdk.v2client import algod
from algosdk.transaction import AssetConfigTxn, AssetTransferTxn, PaymentTxn, AssetOptInTxn, calculate_group_id
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


# Create ASA (UCTZAR)
def create_asa(client, creator, creator_private_key, total):
    params = client.suggested_params()
    txn = AssetConfigTxn(
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
        decimals=6
    )
    signed_txn = txn.sign(creator_private_key)
    tx_id = client.send_transaction(signed_txn)
    response = wait_for_confirmation(client, tx_id)
    return response['asset-index']


# Opt-in to ASA
def opt_in_asa(client, address, private_key, asset_id):
    params = client.suggested_params()
    txn = AssetOptInTxn(address, params, asset_id)
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


# Atomic transaction for adding liquidity
def add_liquidity_atomic(client, sender, sender_pk, pool_address, algo_amount, uctzar_amount, uctzar_id):
    params = client.suggested_params()

    # Create transactions
    algo_txn = PaymentTxn(sender, params, pool_address, algo_amount)
    uctzar_txn = AssetTransferTxn(sender, params, pool_address, uctzar_amount, uctzar_id)

    # Group transactions
    gid = calculate_group_id([algo_txn, uctzar_txn])
    algo_txn.group = gid
    uctzar_txn.group = gid

    # Sign transactions
    signed_algo_txn = algo_txn.sign(sender_pk)
    signed_uctzar_txn = uctzar_txn.sign(sender_pk)

    # Send grouped transactions
    tx_id = client.send_transactions([signed_algo_txn, signed_uctzar_txn])

    wait_for_confirmation(client, tx_id)

    return tx_id


# Atomic transaction for swapping
def swap_atomic(client, sender, sender_pk, pool_address, pool_pk, amount_in, asset_id_in, amount_out, asset_id_out):
    params = client.suggested_params()

    # Create transactions
    if asset_id_in == 0:  # ALGO
        txn_in = PaymentTxn(sender, params, pool_address, amount_in)
    else:
        txn_in = AssetTransferTxn(sender, params, pool_address, amount_in, asset_id_in)

    if asset_id_out == 0:  # ALGO
        txn_out = PaymentTxn(pool_address, params, sender, amount_out)
    else:
        txn_out = AssetTransferTxn(pool_address, params, sender, amount_out, asset_id_out)

    # Group transactions
    gid = calculate_group_id([txn_in, txn_out])
    txn_in.group = gid
    txn_out.group = gid

    # Sign transactions
    signed_txn_in = txn_in.sign(sender_pk)
    signed_txn_out = txn_out.sign(pool_pk)

    # Send grouped transactions
    tx_id = client.send_transactions([signed_txn_in, signed_txn_out])

    wait_for_confirmation(client, tx_id)

    return tx_id


# Main function to simulate the DEX
def main():
    client = create_algod_client()

    # Create accounts
    creator_private_key, creator_address = create_account()
    lp1_private_key, lp1_address = create_account()
    lp2_private_key, lp2_address = create_account()
    trader1_private_key, trader1_address = create_account()
    trader2_private_key, trader2_address = create_account()
    pool_private_key, pool_address = create_account()

    print("Accounts created:")
    print(f"Creator: {creator_address}")
    print(f"LP1: {lp1_address}")
    print(f"LP2: {lp2_address}")
    print(f"Trader1: {trader1_address}")
    print(f"Trader2: {trader2_address}")
    print(f"Pool: {pool_address}")

    # Fund the creator account using the testnet dispenser
    print(f"\nPlease fund the creator account ({creator_address}) using the Algorand testnet dispenser:")
    print("https://bank.testnet.algorand.network/")
    input("Press Enter once you've funded the account...")

    # Check the balance of the creator account
    account_info = client.account_info(creator_address)
    creator_balance = account_info.get('amount')
    print(f"\nCreator account balance: {creator_balance} microALGOs")

    if creator_balance < 2000000:  # Ensure the creator has at least 2 ALGOs
        print("Insufficient funds in creator account. Please add more ALGOs and try again.")
        return

    # Fund accounts
    params = client.suggested_params()
    funding_amount = 300000  # 0.3 ALGOs
    for address in [lp1_address, lp2_address, trader1_address, trader2_address, pool_address]:
        txn = PaymentTxn(creator_address, params, address, funding_amount)
        signed_txn = txn.sign(creator_private_key)
        client.send_transaction(signed_txn)
        wait_for_confirmation(client, signed_txn.get_txid())

    # Create UCTZAR ASA
    uctzar_id = create_asa(client, creator_address, creator_private_key, 1000000000)
    print(f"UCTZAR ASA created with ID: {uctzar_id}")

    # Opt-in to UCTZAR
    for address, pk in [(lp1_address, lp1_private_key), (lp2_address, lp2_private_key),
                        (trader1_address, trader1_private_key), (trader2_address, trader2_private_key),
                        (pool_address, pool_private_key)]:
        opt_in_asa(client, address, pk, uctzar_id)

    # Transfer initial UCTZAR to LPs, traders, and pool
    params = client.suggested_params()
    uctzar_transfer_amount = 100000  # 0.1 UCTZAR
    for address in [lp1_address, lp2_address, trader1_address, trader2_address, pool_address]:
        txn = AssetTransferTxn(creator_address, params, address, uctzar_transfer_amount, uctzar_id)
        signed_txn = txn.sign(creator_private_key)
        client.send_transaction(signed_txn)
        wait_for_confirmation(client, signed_txn.get_txid())

    # Create liquidity pool
    pool = LiquidityPool(100000, 200000)  # 0.1 ALGO = 0.2 UCTZAR
    print("Liquidity pool created")

    # LPs provide liquidity
    add_liquidity_atomic(client, lp1_address, lp1_private_key, pool_address, 50000, 100000, uctzar_id)
    add_liquidity_atomic(client, lp2_address, lp2_private_key, pool_address, 50000, 100000, uctzar_id)
    print("LP1 added liquidity")
    print("LP2 added liquidity")

    # Traders swap tokens
    swap_atomic(client, trader1_address, trader1_private_key, pool_address, pool_private_key, 10000, 0, 19800,
                uctzar_id)  # ALGO to UCTZAR
    print("Trader1 swapped 10000 microALGOs for UCTZAR")

    swap_atomic(client, trader2_address, trader2_private_key, pool_address, pool_private_key, 20000, uctzar_id, 9900,
                0)  # UCTZAR to ALGO
    print("Trader2 swapped 20000 microUCTZAR for ALGOs")

    print("Simulated trading completed")

    # Calculate and distribute fees to LPs (simplified version)
    total_fees = pool.fees
    lp1_fee_share = total_fees / 2
    lp2_fee_share = total_fees / 2
    print(f"LP1 received {lp1_fee_share} microALGOs in fees")
    print(f"LP2 received {lp2_fee_share} microALGOs in fees")

    # LPs withdraw liquidity (simplified version)
    lp1_algo, lp1_uctzar = pool.remove_liquidity(pool.lp_tokens / 2)
    lp2_algo, lp2_uctzar = pool.remove_liquidity(pool.lp_tokens / 2)
    print(f"LP1 withdrew {lp1_algo} microALGOs and {lp1_uctzar} microUCTZAR")
    print(f"LP2 withdrew {lp2_algo} microALGOs and {lp2_uctzar} microUCTZAR")

    print("Final pool state:")
    print(f"ALGO: {pool.algo_amount}")
    print(f"UCTZAR: {pool.uctzar_amount}")
    print(f"LP tokens: {pool.lp_tokens}")
if __name__ == "__main__":
    main()

