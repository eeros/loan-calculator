from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from enum import Enum
from typing import List, Optional, Union
import numpy as np
import numpy_financial as npf

app = FastAPI()

class LoanType(str, Enum):
    annuity = "annuity"
    fixed_amortization = "fixed_amortization"
    fixed_payment = "fixed_payment"

class LoanRepaymentRequest(BaseModel):
    principal: float = 10000
    rate: float = 2.5
    num_payments: int = 12 
    loan_type: LoanType = "annuity"
    initial_fee: float = 100  # Default value as 0.0 if not provided
    payment_fee: float = 3  # Default value as 0.0 if not provided
    balloon_amount: float = 0.0  # Default value as 0.0 if not provided

    payment_number: Optional[int] = None
    

class PaymentDetail(BaseModel):
    payment_number: int
    principal: float
    interest: float
    fee: float 
    total_amount: float  

class AllPaymentsResponse(BaseModel):
    payments: List[PaymentDetail]

def calculate_annuity_payment(principal: float, rate: float, num_payments: int) -> float:
    monthly_interest_rate = rate / 12 / 100
    return (principal * monthly_interest_rate) / (1 - (1 + monthly_interest_rate) ** -num_payments)

def calculate_fixed_payment(principal: float, rate: float, num_payments: int) -> float:
    monthly_interest_rate = rate / 12 / 100
    if monthly_interest_rate == 0:  # Handle zero interest rate
        return principal / num_payments
    return (principal * monthly_interest_rate) / (1 - (1 + monthly_interest_rate) ** -num_payments)

def calculate_fixed_amortization_principal_payment(principal: float, num_payments: int) -> float:
    return principal / num_payments

@app.post("/loan_repayments", response_model=Union[AllPaymentsResponse, PaymentDetail])
async def loan_repayments(request: LoanRepaymentRequest):
    monthly_interest_rate = request.rate / 12 / 100
    remaining_principal = request.principal
    payments_list = []

    for payment_number in range(1, request.num_payments + 1):
        fee_for_payment = request.payment_fee + (request.initial_fee if payment_number == 1 else 0)
        
        if request.loan_type == LoanType.annuity:
            annuity_payment = calculate_annuity_payment(request.principal, request.rate, request.num_payments)
            interest_for_payment = remaining_principal * monthly_interest_rate
            principal_for_payment = annuity_payment - interest_for_payment
            
        elif request.loan_type == LoanType.fixed_payment:
            fixed_payment = calculate_fixed_payment(request.principal, request.rate, request.num_payments)
            interest_for_payment = remaining_principal * monthly_interest_rate
            principal_for_payment = fixed_payment - interest_for_payment
            
        elif request.loan_type == LoanType.fixed_amortization:
            principal_for_payment = request.principal / request.num_payments
            interest_for_payment = remaining_principal * monthly_interest_rate

        total_payment = principal_for_payment + interest_for_payment + fee_for_payment
        
        # Adjust for balloon payment on the final payment
        if payment_number == request.num_payments:
            total_payment += request.balloon_amount
            principal_for_payment += request.balloon_amount  # Adjust principal for balloon amount
        
        remaining_principal -= (principal_for_payment - request.balloon_amount if payment_number == request.num_payments else principal_for_payment)
        
        payments_list.append(PaymentDetail(payment_number=payment_number, principal=principal_for_payment, interest=interest_for_payment, fee=fee_for_payment, total_amount=total_payment))

        if request.payment_number and payment_number == request.payment_number:
            return payments_list[-1]  # Return the specific requested payment detail

    if request.payment_number:
        raise HTTPException(status_code=404, detail=f"Payment number {request.payment_number} is out of range.")
    return AllPaymentsResponse(payments=payments_list)

@app.post("/total_sum", response_model=PaymentDetail)
async def total_sum(request: LoanRepaymentRequest):
    all_payments_response = await loan_repayments(request)
    total_principal = sum(payment.principal for payment in all_payments_response.payments)
    total_interest = sum(payment.interest for payment in all_payments_response.payments)
    total_fee = sum(payment.fee for payment in all_payments_response.payments)
    total_amount = sum(payment.total_amount for payment in all_payments_response.payments)

    return PaymentDetail(
        payment_number=0,  # Using 0 to indicate total sum instead of a specific payment
        principal=total_principal,
        interest=total_interest,
        fee=total_fee,
        total_amount=total_amount
    )

def calculate_effective_interest_rate(request: LoanRepaymentRequest) -> float:
    cash_flows = [-request.principal]  # Initial loan amount as a negative cash flow

    if request.loan_type == LoanType.annuity:
        # Calculate the annuity payment
        annuity_payment = calculate_annuity_payment(request.principal, request.rate, request.num_payments)
        # Include the initial fee with the first payment
        cash_flows.append(annuity_payment + request.initial_fee + request.payment_fee)  # First payment adjusted for initial fee

        # Regular annuity payments for the remaining periods, with payment fee
        for _ in range(2, request.num_payments):
            cash_flows.append(annuity_payment + request.payment_fee)
        
        # Adjust the last payment for any balloon amount
        cash_flows.append(annuity_payment + request.payment_fee + request.balloon_amount)

    elif request.loan_type == LoanType.fixed_payment:
        # Calculate the fixed payment
        fixed_payment = calculate_fixed_payment(request.principal, request.rate, request.num_payments)
        # Include the initial fee with the first payment
        cash_flows.append(fixed_payment + request.initial_fee + request.payment_fee)  # First payment adjusted for initial fee

        # Regular fixed payments for the remaining periods, with payment fee
        for _ in range(2, request.num_payments):
            cash_flows.append(fixed_payment + request.payment_fee)
        
        # Adjust the last payment for any balloon amount
        cash_flows.append(fixed_payment + request.payment_fee + request.balloon_amount)

    elif request.loan_type == LoanType.fixed_amortization:
        remaining_principal = request.principal
        principal_payment = calculate_fixed_amortization_principal_payment(request.principal, request.num_payments)

        # Include the initial fee with the first payment's interest and fee
        first_interest_payment = remaining_principal * (request.rate / 12 / 100)
        cash_flows.append(principal_payment + first_interest_payment + request.initial_fee + request.payment_fee)  # First payment adjusted

        # Regular payments for the remaining periods
        for _ in range(2, request.num_payments):
            remaining_principal -= principal_payment
            interest_payment = remaining_principal * (request.rate / 12 / 100)
            cash_flows.append(principal_payment + interest_payment + request.payment_fee)
        
        # Adjust the last payment for any balloon amount
        last_interest_payment = remaining_principal * (request.rate / 12 / 100)
        cash_flows.append(principal_payment + last_interest_payment + request.payment_fee + request.balloon_amount)

    # Calculate the internal rate of return (IRR) from cash flows
    monthly_irr = npf.irr(cash_flows)

    # Convert monthly IRR to annual effective interest rate
    annual_eir = (1 + monthly_irr) ** 12 - 1

    return annual_eir


@app.post("/effective_interest_rate", response_model=float)
async def effective_interest_rate(request: LoanRepaymentRequest) -> float:
    return calculate_effective_interest_rate(request)

