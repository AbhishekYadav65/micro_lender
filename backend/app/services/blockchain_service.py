"""
Resilient BlockchainService for local dev and real chain.
- If a real contract and account are configured, calls go on-chain.
- If not, uses a local JSON ledger at storage/loans.json so endpoints behave predictably for testing.
"""

import os
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional, Any

from web3 import Web3
from web3.middleware import geth_poa_middleware
from eth_account import Account

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BlockchainService:
    def __init__(self):
        # Config
        self.rpc_url = os.getenv("ETHEREUM_RPC_URL", "http://localhost:8545")
        self.chain_id = int(os.getenv("CHAIN_ID", "1337"))
        self.private_key = os.getenv("PRIVATE_KEY", "")  # optional for read-only
        self.contract_address = os.getenv("CONTRACT_ADDRESS", "").strip()

        # Web3 initialization (may be unreachable - handled below)
        try:
            self.w3 = Web3(Web3.HTTPProvider(self.rpc_url))
            # inject PoA middleware if needed (safe to call even if not used)
            self.w3.middleware_onion.inject(geth_poa_middleware, layer=0)
            logger.info(f"Web3 provider set to {self.rpc_url}")
        except Exception as e:
            logger.warning(f"Failed to initialize Web3 provider: {e}")
            self.w3 = None

        # Account handling
        if self.private_key:
            try:
                self.account = Account.from_key(self.private_key)
                logger.info(f"Loaded account: {self.account.address}")
            except Exception as e:
                logger.error(f"Invalid private key: {e}")
                self.account = None
        else:
            self.account = None
            logger.info("No PRIVATE_KEY configured — service may be read-only or use local ledger")

        # Contract and ABI loading
        self.contract = None
        self.abi = None
        self._load_contract()

        # Local fallback ledger for testing without a deployed contract
        storage_dir = Path(os.getenv("STORAGE_PATH", "./storage"))
        storage_dir.mkdir(parents=True, exist_ok=True)
        self._ledger_path = storage_dir / "loans.json"
        self._ensure_ledger_loaded()

        # Loan counter for local ledger
        self._local_counter = max([int(k) for k in self._ledger.keys()], default=0)

    # -----------------------------
    # Contract / ABI helpers
    # -----------------------------
    def _load_contract(self) -> None:
        """Attempt to load ABI and attach contract if address present."""
        try:
            # Prefer an artifacts JSON if present
            abi_candidate = Path(__file__).resolve().parents[1] / "contracts" / "artifacts" / "LoanEscrow.json"
            if abi_candidate.exists():
                try:
                    with open(abi_candidate, "r", encoding="utf-8") as f:
                        contract_json = json.load(f)
                        self.abi = contract_json.get("abi", None) or contract_json
                except Exception as e:
                    logger.warning(f"Failed to read ABI from artifacts: {e}")
                    self.abi = None
            else:
                self.abi = self._minimal_abi()

            if self.contract_address and self.w3 and self.abi:
                if Web3.is_address(self.contract_address):
                    checksum = Web3.to_checksum_address(self.contract_address)
                    self.contract = self.w3.eth.contract(address=checksum, abi=self.abi)
                    logger.info(f"Contract attached at {checksum}")
                else:
                    logger.warning("CONTRACT_ADDRESS present but not a valid Ethereum address.")
            else:
                if not self.contract_address:
                    logger.info("No CONTRACT_ADDRESS configured — using local ledger fallback.")
                if not self.w3:
                    logger.info("Web3 provider not available — using local ledger fallback.")
        except Exception as e:
            logger.error(f"_load_contract error: {e}", exc_info=True)
            self.contract = None

    def _minimal_abi(self) -> List[Dict[str, Any]]:
        # Minimal ABI used earlier; keep core functions (getBorrowerLoans optional)
        return [
            {
                "inputs": [
                    {"name": "_principal", "type": "uint256"},
                    {"name": "_termDays", "type": "uint256"},
                    {"name": "_interestRate", "type": "uint256"},
                    {"name": "_kycHash", "type": "bytes32"},
                    {"name": "_explanationHash", "type": "bytes32"},
                    {"name": "_riskCategory", "type": "uint8"},
                    {"name": "_probabilityOfDefault", "type": "uint256"}
                ],
                "name": "createLoan",
                "outputs": [{"name": "", "type": "uint256"}],
                "stateMutability": "nonpayable",
                "type": "function"
            },
            {"inputs": [{"name": "_loanId", "type": "uint256"}], "name": "fundLoan", "outputs": [], "stateMutability": "payable", "type": "function"},
            {"inputs": [{"name": "_loanId", "type": "uint256"}], "name": "disburse", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"name": "_loanId", "type": "uint256"}], "name": "repay", "outputs": [], "stateMutability": "payable", "type": "function"},
            {"inputs": [{"name": "_loanId", "type": "uint256"}], "name": "withdraw", "outputs": [], "stateMutability": "nonpayable", "type": "function"},
            {"inputs": [{"name": "_loanId", "type": "uint256"}], "name": "getLoan", "outputs": [{"components": [
                {"name":"loanId","type":"uint256"},{"name":"borrower","type":"address"},{"name":"principal","type":"uint256"},
                {"name":"interestRate","type":"uint256"},{"name":"termDays","type":"uint256"},{"name":"totalRepayment","type":"uint256"},
                {"name":"amountRepaid","type":"uint256"},{"name":"status","type":"uint8"},{"name":"kycHash","type":"bytes32"},
                {"name":"explanationHash","type":"bytes32"}],"name":"","type":"tuple"}],"stateMutability":"view","type":"function"}
        ]

    # -----------------------------
    # Local ledger (fallback)
    # -----------------------------
    def _ensure_ledger_loaded(self) -> None:
        try:
            if self._ledger_path.exists():
                with open(self._ledger_path, "r", encoding="utf-8") as f:
                    self._ledger = json.load(f)
            else:
                self._ledger = {}
                self._persist_ledger()
        except Exception as e:
            logger.error(f"Failed to load local ledger: {e}", exc_info=True)
            self._ledger = {}

    def _persist_ledger(self) -> None:
        try:
            with open(self._ledger_path, "w", encoding="utf-8") as f:
                json.dump(self._ledger, f, indent=2, ensure_ascii=False)
        except Exception as e:
            logger.error(f"Failed to persist ledger: {e}", exc_info=True)

    def _next_local_id(self) -> int:
        self._local_counter += 1
        return self._local_counter

    # -----------------------------
    # Utility converters
    # -----------------------------
    def _to_bytes32(self, value: str) -> bytes:
        """Convert hex string or text to 32-byte value for solidity bytes32."""
        try:
            if value.startswith("0x") and len(value) >= 4:
                return Web3.to_bytes(hexstr=value)
            return Web3.keccak(text=value)
        except Exception:
            return Web3.keccak(text=str(value))

    def _wei(self, eth_amount: float) -> int:
        if self.w3:
            return self.w3.to_wei(eth_amount, "ether")
        # fallback convert
        return int(eth_amount * (10 ** 18))

    def _from_wei(self, wei_amount: int) -> float:
        if self.w3:
            return self.w3.from_wei(wei_amount, "ether")
        return float(wei_amount) / (10 ** 18)

    # -----------------------------
    # Core functions (on-chain or ledger)
    # -----------------------------
    def create_loan(
        self,
        principal: float,
        term_days: int,
        interest_rate: int,
        kyc_hash: str,
        explanation_hash: str,
        risk_category: str,
        probability_of_default: int,
        borrower_address: str
    ) -> Dict[str, Any]:
        # If contract present, attempt on-chain creation; else use ledger fallback
        try:
            if self.contract and self.account:
                # Prepare bytes32
                kyc_b = self._to_bytes32(kyc_hash)
                expl_b = self._to_bytes32(explanation_hash)
                rc_map = {"Low": 0, "Medium": 1, "High": 2}
                rc_val = rc_map.get(risk_category, 1)

                principal_wei = self._wei(principal)

                nonce = self.w3.eth.get_transaction_count(self.account.address)
                # Estimate gas (safe guard)
                try:
                    gas_est = self.contract.functions.createLoan(
                        principal_wei, term_days, interest_rate, kyc_b, expl_b, rc_val, probability_of_default
                    ).estimate_gas({"from": self.account.address})
                except Exception:
                    gas_est = 300000

                tx = self.contract.functions.createLoan(
                    principal_wei, term_days, interest_rate, kyc_b, expl_b, rc_val, probability_of_default
                ).build_transaction({
                    "from": self.account.address,
                    "gas": gas_est + 50000,
                    "gasPrice": self.w3.eth.gas_price,
                    "nonce": nonce,
                    "chainId": self.chain_id
                })

                signed = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)

                if receipt and receipt.get("status", 0) == 1:
                    loan_id = self._parse_loan_created_event(receipt) or 0
                    return {"success": True, "loan_id": int(loan_id), "tx_hash": tx_hash.hex(), "block_number": receipt.get("blockNumber"), "gas_used": receipt.get("gasUsed")}
                return {"success": False, "error": "tx_failed", "tx_hash": tx_hash.hex()}
            else:
                # Local ledger fallback
                lid = self._next_local_id()
                entry = {
                    "loan_id": lid,
                    "borrower": borrower_address,
                    "principal": principal,
                    "interest_rate": interest_rate,
                    "term_days": term_days,
                    "total_repayment": round(principal * (1 + interest_rate / 10000 * term_days / 365), 8),
                    "amount_repaid": 0.0,
                    "status": "Pending",
                    "kyc_hash": kyc_hash,
                    "explanation_hash": explanation_hash,
                    "risk_category": risk_category,
                    "probability_of_default": probability_of_default
                }
                self._ledger[str(lid)] = entry
                self._persist_ledger()
                logger.info(f"Local ledger: created loan {lid}")
                return {"success": True, "loan_id": lid, "tx_hash": None}
        except Exception as e:
            logger.error(f"create_loan error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def fund_loan(self, loan_id: int, amount: float, lender_address: str) -> Dict[str, Any]:
        try:
            if self.contract and self.account:
                amount_wei = self._wei(amount)
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                tx = self.contract.functions.fundLoan(loan_id).build_transaction({
                    "from": self.account.address,
                    "value": amount_wei,
                    "gas": 300000,
                    "gasPrice": self.w3.eth.gas_price,
                    "nonce": nonce,
                    "chainId": self.chain_id
                })
                signed = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
                return {"success": receipt.get("status", 0) == 1, "tx_hash": tx_hash.hex(), "gas_used": receipt.get("gasUsed")}
            else:
                key = str(loan_id)
                if key not in self._ledger:
                    return {"success": False, "error": "loan_not_found"}
                # For simplicity treat full funding if amount >= principal
                entry = self._ledger[key]
                entry["funded_amount"] = entry.get("funded_amount", 0.0) + amount
                if entry["funded_amount"] >= entry["principal"]:
                    entry["status"] = "Funded"
                self._persist_ledger()
                return {"success": True, "tx_hash": None}
        except Exception as e:
            logger.error(f"fund_loan error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def disburse_loan(self, loan_id: int, borrower_address: str) -> Dict[str, Any]:
        try:
            if self.contract and self.account:
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                tx = self.contract.functions.disburse(loan_id).build_transaction({
                    "from": self.account.address,
                    "gas": 200000,
                    "gasPrice": self.w3.eth.gas_price,
                    "nonce": nonce,
                    "chainId": self.chain_id
                })
                signed = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
                return {"success": receipt.get("status", 0) == 1, "tx_hash": tx_hash.hex()}
            else:
                key = str(loan_id)
                if key not in self._ledger:
                    return {"success": False, "error": "loan_not_found"}
                self._ledger[key]["status"] = "Disbursed"
                self._persist_ledger()
                return {"success": True, "tx_hash": None}
        except Exception as e:
            logger.error(f"disburse_loan error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def repay_loan(self, loan_id: int, amount: float, borrower_address: str) -> Dict[str, Any]:
        try:
            if self.contract and self.account:
                amount_wei = self._wei(amount)
                nonce = self.w3.eth.get_transaction_count(self.account.address)
                tx = self.contract.functions.repay(loan_id).build_transaction({
                    "from": self.account.address,
                    "value": amount_wei,
                    "gas": 200000,
                    "gasPrice": self.w3.eth.gas_price,
                    "nonce": nonce,
                    "chainId": self.chain_id
                })
                signed = self.w3.eth.account.sign_transaction(tx, private_key=self.private_key)
                tx_hash = self.w3.eth.send_raw_transaction(signed.rawTransaction)
                receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=300)
                return {"success": receipt.get("status", 0) == 1, "tx_hash": tx_hash.hex()}
            else:
                key = str(loan_id)
                if key not in self._ledger:
                    return {"success": False, "error": "loan_not_found"}
                entry = self._ledger[key]
                entry["amount_repaid"] = round(entry.get("amount_repaid", 0.0) + amount, 8)
                if entry["amount_repaid"] >= entry["total_repayment"]:
                    entry["status"] = "Repaid"
                self._persist_ledger()
                return {"success": True, "tx_hash": None}
        except Exception as e:
            logger.error(f"repay_loan error: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    def get_loan(self, loan_id: int) -> Optional[Dict[str, Any]]:
        try:
            if self.contract:
                loan_raw = self.contract.functions.getLoan(loan_id).call()
                return {
                    "loan_id": int(loan_raw[0]),
                    "borrower": loan_raw[1],
                    "principal": float(self._from_wei(loan_raw[2])),
                    "interest_rate": int(loan_raw[3]),
                    "term_days": int(loan_raw[4]),
                    "total_repayment": float(self._from_wei(loan_raw[5])),
                    "amount_repaid": float(self._from_wei(loan_raw[6])),
                    "status": int(loan_raw[7]),
                    "kyc_hash": loan_raw[8].hex() if hasattr(loan_raw[8], "hex") else str(loan_raw[8]),
                    "explanation_hash": loan_raw[9].hex() if hasattr(loan_raw[9], "hex") else str(loan_raw[9])
                }
            else:
                return self._ledger.get(str(loan_id))
        except Exception as e:
            logger.error(f"get_loan error: {e}", exc_info=True)
            return None

    def get_borrower_loans(self, address: str) -> List[int]:
        try:
            if self.contract:
                # If contract supports it, call; otherwise empty list
                try:
                    ids = self.contract.functions.getBorrowerLoans(Web3.to_checksum_address(address)).call()
                    return [int(i) for i in ids]
                except Exception:
                    return []
            else:
                out = []
                for k, v in self._ledger.items():
                    if v.get("borrower", "").lower() == address.lower():
                        out.append(int(k))
                return out
        except Exception as e:
            logger.error(f"get_borrower_loans error: {e}", exc_info=True)
            return []

    # -----------------------------
    # Event parsing helpers
    # -----------------------------
    def _parse_loan_created_event(self, tx_receipt: Dict[str, Any]) -> Optional[int]:
        try:
            if not self.contract:
                return None
            try:
                logs = self.contract.events.LoanCreated().process_receipt(tx_receipt)
                if logs and len(logs) > 0:
                    return int(logs[0]["args"].get("loanId", 0))
            except Exception:
                # best-effort fallback
                for log in tx_receipt.get("logs", []):
                    # do not assume topic decoding here; return None as fallback
                    continue
            return None
        except Exception as e:
            logger.error(f"_parse_loan_created_event error: {e}", exc_info=True)
            return None

    # -----------------------------
    # Health
    # -----------------------------
    def check_health(self) -> bool:
        # healthy if either web3 connected OR local ledger available
        try:
            web3_ok = False
            if self.w3:
                try:
                    web3_ok = self.w3.is_connected()
                except Exception:
                    web3_ok = False
            ledger_ok = isinstance(self._ledger, dict)
            return web3_ok or ledger_ok
        except Exception:
            return False
