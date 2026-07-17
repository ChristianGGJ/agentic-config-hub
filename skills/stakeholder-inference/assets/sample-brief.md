# Project Brief: Aurora Customer Payments Portal

## Sponsor statement

Aurora Energy, a regional electricity utility serving roughly 400,000
households, wants a self-service web portal where residential customers can
view their monthly bills and pay them online by debit or credit card. The
CFO is funding the initiative and expects it to cut call-center payment
handling by half within a year of launch.

## Scope description

- Customers create an account with their email address and account number,
  view current and historical bills, and pay by card.
- Card payments are processed through an external payment gateway vendor;
  Aurora does not want to store card numbers itself.
- The portal runs on a public cloud hosting provider under an existing
  enterprise agreement.
- The customer support team takes over payment disputes, failed payments,
  and account-lockout tickets raised through the portal.
- A small platform team carries the on-call pager for portal availability.
- Bills contain customer names, addresses, consumption history, and payment
  status - personal data of residents in an EU member state.
- Paper billing continues for customers who do not enroll; the portal must
  not degrade service for offline customers, many of them elderly.

## Constraints

- Launch before the next regulated billing-cycle change.
- The energy market regulator audits billing accuracy annually.
- Budget approved for one external vendor (the payment gateway) only.

## Out of scope

- Direct-debit mandates and bank transfers (phase 2).
- A native mobile app (the portal must be responsive web only).
