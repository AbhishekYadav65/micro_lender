// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/access/Ownable.sol";

/**
 * @title LoanEscrow
 * @dev P2P Micro-Lending Platform with KYC and AI/ML Risk Assessment
 * @notice This contract manages loan creation, funding, disbursement, and repayment
 */
contract LoanEscrow is ReentrancyGuard, Ownable {
    
    // Loan status enumeration
    enum LoanStatus {
        Pending,      // Loan created, awaiting funding
        Funded,       // Fully funded by lenders
        Disbursed,    // Funds disbursed to borrower
        Repaid,       // Fully repaid
        Defaulted     // Loan defaulted
    }
    
    // Risk category enumeration
    enum RiskCategory {
        Low,
        Medium,
        High
    }
    
    // Loan structure
    struct Loan {
        uint256 loanId;
        address borrower;
        uint256 principal;           // Principal amount in wei
        uint256 interestRate;        // Annual interest rate (basis points, e.g., 1000 = 10%)
        uint256 termDays;            // Loan term in days
        uint256 totalRepayment;      // Total amount to be repaid
        uint256 amountRepaid;        // Amount repaid so far
        uint256 createdAt;           // Timestamp of loan creation
        uint256 fundedAt;            // Timestamp when fully funded
        uint256 disbursedAt;         // Timestamp of disbursement
        uint256 dueDate;             // Repayment due date
        LoanStatus status;
        bytes32 kycHash;             // SHA256 hash of KYC data
        bytes32 explanationHash;     // SHA256 hash of ML explanation
        RiskCategory riskCategory;
        uint256 probabilityOfDefault; // PD in basis points (e.g., 250 = 2.5%)
    }
    
    // Lender contribution structure
    struct Contribution {
        address lender;
        uint256 amount;
        bool withdrawn;
    }
    
    // State variables
    uint256 public loanCounter;
    uint256 public platformFeeRate = 100; // 1% in basis points
    uint256 public latePenaltyRate = 500; // 5% in basis points
    
    mapping(uint256 => Loan) public loans;
    mapping(uint256 => Contribution[]) public loanContributions;
    mapping(uint256 => mapping(address => uint256)) public lenderContributions;
    mapping(address => uint256[]) public borrowerLoans;
    mapping(address => uint256[]) public lenderLoans;
    
    // Events
    event LoanCreated(
        uint256 indexed loanId,
        address indexed borrower,
        uint256 principal,
        uint256 interestRate,
        uint256 termDays,
        bytes32 kycHash,
        bytes32 explanationHash,
        RiskCategory riskCategory,
        uint256 probabilityOfDefault
    );
    
    event LoanFunded(
        uint256 indexed loanId,
        address indexed lender,
        uint256 amount,
        uint256 totalFunded
    );
    
    event LoanFullyFunded(
        uint256 indexed loanId,
        uint256 timestamp
    );
    
    event LoanDisbursed(
        uint256 indexed loanId,
        address indexed borrower,
        uint256 amount,
        uint256 timestamp
    );
    
    event RepaymentMade(
        uint256 indexed loanId,
        address indexed borrower,
        uint256 amount,
        uint256 totalRepaid,
        uint256 timestamp
    );
    
    event LoanRepaid(
        uint256 indexed loanId,
        uint256 timestamp
    );
    
    event LoanDefaulted(
        uint256 indexed loanId,
        uint256 timestamp
    );
    
    event LenderWithdrawal(
        uint256 indexed loanId,
        address indexed lender,
        uint256 amount,
        uint256 timestamp
    );
    
    event PlatformFeeCollected(
        uint256 indexed loanId,
        uint256 amount
    );
    
    // Modifiers
    modifier onlyBorrower(uint256 _loanId) {
        require(loans[_loanId].borrower == msg.sender, "Not the borrower");
        _;
    }
    
    modifier loanExists(uint256 _loanId) {
        require(_loanId > 0 && _loanId <= loanCounter, "Loan does not exist");
        _;
    }
    
    modifier loanInStatus(uint256 _loanId, LoanStatus _status) {
        require(loans[_loanId].status == _status, "Invalid loan status");
        _;
    }
    
    constructor() Ownable(msg.sender) {}
    
    /**
     * @dev Create a new loan request
     * @param _principal Principal amount in wei
     * @param _termDays Loan term in days
     * @param _interestRate Annual interest rate in basis points
     * @param _kycHash SHA256 hash of KYC JSON
     * @param _explanationHash SHA256 hash of ML explanation JSON
     * @param _riskCategory Risk category from ML model
     * @param _probabilityOfDefault PD in basis points
     */
    function createLoan(
        uint256 _principal,
        uint256 _termDays,
        uint256 _interestRate,
        bytes32 _kycHash,
        bytes32 _explanationHash,
        RiskCategory _riskCategory,
        uint256 _probabilityOfDefault
    ) external returns (uint256) {
        require(_principal > 0, "Principal must be greater than 0");
        require(_termDays > 0, "Term must be greater than 0");
        require(_interestRate > 0 && _interestRate <= 10000, "Invalid interest rate");
        require(_kycHash != bytes32(0), "KYC hash required");
        require(_explanationHash != bytes32(0), "Explanation hash required");
        require(_probabilityOfDefault <= 10000, "Invalid PD");
        
        loanCounter++;
        
        // Calculate total repayment: principal + interest
        // Interest = (principal * rate * days) / (365 * 10000)
        uint256 interest = (_principal * _interestRate * _termDays) / (365 * 10000);
        uint256 totalRepayment = _principal + interest;
        
        loans[loanCounter] = Loan({
            loanId: loanCounter,
            borrower: msg.sender,
            principal: _principal,
            interestRate: _interestRate,
            termDays: _termDays,
            totalRepayment: totalRepayment,
            amountRepaid: 0,
            createdAt: block.timestamp,
            fundedAt: 0,
            disbursedAt: 0,
            dueDate: 0,
            status: LoanStatus.Pending,
            kycHash: _kycHash,
            explanationHash: _explanationHash,
            riskCategory: _riskCategory,
            probabilityOfDefault: _probabilityOfDefault
        });
        
        borrowerLoans[msg.sender].push(loanCounter);
        
        emit LoanCreated(
            loanCounter,
            msg.sender,
            _principal,
            _interestRate,
            _termDays,
            _kycHash,
            _explanationHash,
            _riskCategory,
            _probabilityOfDefault
        );
        
        return loanCounter;
    }
    
    /**
     * @dev Fund a loan (partial or full)
     * @param _loanId The loan ID to fund
     */
    function fundLoan(uint256 _loanId) 
        external 
        payable 
        nonReentrant 
        loanExists(_loanId) 
        loanInStatus(_loanId, LoanStatus.Pending) 
    {
        require(msg.value > 0, "Funding amount must be greater than 0");
        Loan storage loan = loans[_loanId];
        require(msg.sender != loan.borrower, "Borrower cannot fund own loan");
        
        // Calculate current funding level
        uint256 currentFunding = 0;
        for (uint256 i = 0; i < loanContributions[_loanId].length; i++) {
            currentFunding += loanContributions[_loanId][i].amount;
        }
        
        uint256 remainingFunding = loan.principal - currentFunding;
        require(remainingFunding > 0, "Loan already fully funded");
        
        // Limit contribution to remaining amount needed
        uint256 contribution = msg.value > remainingFunding ? remainingFunding : msg.value;
        
        // Record contribution
        loanContributions[_loanId].push(Contribution({
            lender: msg.sender,
            amount: contribution,
            withdrawn: false
        }));
        
        lenderContributions[_loanId][msg.sender] += contribution;
        lenderLoans[msg.sender].push(_loanId);
        
        emit LoanFunded(_loanId, msg.sender, contribution, currentFunding + contribution);
        
        // Check if loan is now fully funded
        if (currentFunding + contribution >= loan.principal) {
            loan.status = LoanStatus.Funded;
            loan.fundedAt = block.timestamp;
            emit LoanFullyFunded(_loanId, block.timestamp);
        }
        
        // Refund excess amount
        if (msg.value > contribution) {
            (bool success, ) = msg.sender.call{value: msg.value - contribution}("");
            require(success, "Refund failed");
        }
    }
    
    /**
     * @dev Disburse loan funds to borrower
     * @param _loanId The loan ID to disburse
     */
    function disburse(uint256 _loanId) 
        external 
        nonReentrant 
        loanExists(_loanId) 
        loanInStatus(_loanId, LoanStatus.Funded) 
        onlyBorrower(_loanId) 
    {
        Loan storage loan = loans[_loanId];
        
        // Calculate platform fee
        uint256 platformFee = (loan.principal * platformFeeRate) / 10000;
        uint256 disbursementAmount = loan.principal - platformFee;
        
        // Update loan status
        loan.status = LoanStatus.Disbursed;
        loan.disbursedAt = block.timestamp;
        loan.dueDate = block.timestamp + (loan.termDays * 1 days);
        
        // Transfer funds to borrower
        (bool success, ) = loan.borrower.call{value: disbursementAmount}("");
        require(success, "Disbursement failed");
        
        // Transfer platform fee to owner
        (bool feeSuccess, ) = owner().call{value: platformFee}("");
        require(feeSuccess, "Fee transfer failed");
        
        emit LoanDisbursed(_loanId, loan.borrower, disbursementAmount, block.timestamp);
        emit PlatformFeeCollected(_loanId, platformFee);
    }
    
    /**
     * @dev Make a repayment on a loan
     * @param _loanId The loan ID to repay
     */
    function repay(uint256 _loanId) 
        external 
        payable 
        nonReentrant 
        loanExists(_loanId) 
        loanInStatus(_loanId, LoanStatus.Disbursed) 
    {
        require(msg.value > 0, "Repayment amount must be greater than 0");
        Loan storage loan = loans[_loanId];
        
        uint256 amountDue = loan.totalRepayment - loan.amountRepaid;
        
        // Apply late penalty if past due date
        if (block.timestamp > loan.dueDate) {
            uint256 daysLate = (block.timestamp - loan.dueDate) / 1 days;
            uint256 latePenalty = (loan.totalRepayment * latePenaltyRate * daysLate) / (365 * 10000);
            amountDue += latePenalty;
        }
        
        require(msg.value <= amountDue, "Overpayment not allowed");
        
        loan.amountRepaid += msg.value;
        
        emit RepaymentMade(_loanId, msg.sender, msg.value, loan.amountRepaid, block.timestamp);
        
        // Check if loan is fully repaid
        if (loan.amountRepaid >= loan.totalRepayment) {
            loan.status = LoanStatus.Repaid;
            emit LoanRepaid(_loanId, block.timestamp);
        }
    }
    
    /**
     * @dev Mark a loan as defaulted (only owner or after grace period)
     * @param _loanId The loan ID to mark as defaulted
     */
    function markDefault(uint256 _loanId) 
        external 
        loanExists(_loanId) 
        loanInStatus(_loanId, LoanStatus.Disbursed) 
    {
        Loan storage loan = loans[_loanId];
        
        // Allow owner to mark default anytime after due date
        // Or allow anyone after 30 days past due
        uint256 gracePeriod = 30 days;
        require(
            (msg.sender == owner() && block.timestamp > loan.dueDate) ||
            (block.timestamp > loan.dueDate + gracePeriod),
            "Cannot mark as default yet"
        );
        
        loan.status = LoanStatus.Defaulted;
        emit LoanDefaulted(_loanId, block.timestamp);
    }
    
    /**
     * @dev Withdraw repayment funds (for lenders)
     * @param _loanId The loan ID to withdraw from
     */
    function withdraw(uint256 _loanId) 
        external 
        nonReentrant 
        loanExists(_loanId) 
    {
        Loan storage loan = loans[_loanId];
        require(
            loan.status == LoanStatus.Repaid || loan.status == LoanStatus.Defaulted,
            "Loan not settled"
        );
        
        uint256 lenderContribution = lenderContributions[_loanId][msg.sender];
        require(lenderContribution > 0, "No contribution found");
        
        // Find and mark contribution as withdrawn
        bool found = false;
        for (uint256 i = 0; i < loanContributions[_loanId].length; i++) {
            if (loanContributions[_loanId][i].lender == msg.sender && 
                !loanContributions[_loanId][i].withdrawn) {
                loanContributions[_loanId][i].withdrawn = true;
                found = true;
            }
        }
        require(found, "Already withdrawn");
        
        // Calculate lender's share
        uint256 lenderShare = (loan.amountRepaid * lenderContribution) / loan.principal;
        
        require(lenderShare > 0, "No funds to withdraw");
        
        // Transfer funds
        (bool success, ) = msg.sender.call{value: lenderShare}("");
        require(success, "Withdrawal failed");
        
        emit LenderWithdrawal(_loanId, msg.sender, lenderShare, block.timestamp);
    }
    
    /**
     * @dev Get loan details
     * @param _loanId The loan ID
     */
    function getLoan(uint256 _loanId) 
        external 
        view 
        loanExists(_loanId) 
        returns (Loan memory) 
    {
        return loans[_loanId];
    }
    
    /**
     * @dev Get all contributions for a loan
     * @param _loanId The loan ID
     */
    function getLoanContributions(uint256 _loanId) 
        external 
        view 
        loanExists(_loanId) 
        returns (Contribution[] memory) 
    {
        return loanContributions[_loanId];
    }
    
    /**
     * @dev Get borrower's loan IDs
     * @param _borrower The borrower address
     */
    function getBorrowerLoans(address _borrower) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return borrowerLoans[_borrower];
    }
    
    /**
     * @dev Get lender's loan IDs
     * @param _lender The lender address
     */
    function getLenderLoans(address _lender) 
        external 
        view 
        returns (uint256[] memory) 
    {
        return lenderLoans[_lender];
    }
    
    /**
     * @dev Update platform fee rate (only owner)
     * @param _newRate New fee rate in basis points
     */
    function setPlatformFeeRate(uint256 _newRate) external onlyOwner {
        require(_newRate <= 1000, "Fee rate too high"); // Max 10%
        platformFeeRate = _newRate;
    }
    
    /**
     * @dev Update late penalty rate (only owner)
     * @param _newRate New penalty rate in basis points
     */
    function setLatePenaltyRate(uint256 _newRate) external onlyOwner {
        require(_newRate <= 2000, "Penalty rate too high"); // Max 20%
        latePenaltyRate = _newRate;
    }
}