# TESA Cloud Engineering

Labs, design exercises and infrastructure code from the **TeSA Cloud Engineering Cohort** (February to April 2026), rebuilt, corrected and tested after the programme: AWS networking, security groups and network ACLs, EC2, S3, RDS, Terraform and CI/CD, with AWS architecture diagrams.

[![shell](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/shell.yml/badge.svg)](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/shell.yml)
[![python](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/python.yml/badge.svg)](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/python.yml)

## About the programme

The Tech Skills Accelerator Programme (TeSA), run by Univaciti, is an intensive hybrid programme in Nigeria. I completed its Cloud Engineering cohort between February and April 2026, finishing with an internship week at a cloud consultancy, and was awarded a graduation cash prize by the CEO for technical performance.

## What this repository is, and is not

This is not an archive of submissions. Each module takes something I did during the programme and rebuilds it to the standard I would ship today:

- **Problems are restated in my own words.** No course material, exercise briefs or slides are reproduced.
- **Mistakes are fixed and shown.** Every module has a "Mistakes I fixed" section that names what was wrong in my original work and what changed.
- **Labs are compared with production.** Every module ends with a table showing how the lab would change in production, tagged by [AWS Well-Architected](https://aws.amazon.com/architecture/well-architected/) pillar.
- **Evidence is redacted.** Account IDs, IP addresses, user names and other people's details are removed from transcripts and screenshots. The training sandbox the labs ran in has since been decommissioned.
- **Design studies are anonymised.** Company names, domains and address ranges in the design studies are fictional, and client details from the internship week are withheld.

## Modules

✅ done | ⬜ planned

| # | Module | What it shows | Status |
|---|---|---|---|
| 01 | [Linux Fundamentals](01-linux-fundamentals/) | Bash backup and restore with checksums, strict mode and automated tests | ✅ |
| 02 | [Cloud Deployment Models](02-cloud-deployment-models/) | Hybrid design for a regulated bank: data residency, latency, recovery, two decision records | ✅ |
| 03 | [VPC and CIDR Design](03-vpc-cidr-design/) | A tested Python tool that plans right-sized, non-overlapping subnets across Availability Zones | ✅ |
| 04 | Public and Private Subnets | Tiered VPC across two Availability Zones, load balancer, NAT | ⬜ |
| 05 | Route Tables and Routing | Internet gateway, NAT gateway, local routes, route evaluation | ⬜ |
| 06 | Security Groups vs Network ACLs | Stateful and stateless filtering, numbered rule tables | ⬜ |
| 07 | EC2 Web Server | Apache on Ubuntu, user data, troubleshooting a port conflict | ⬜ |
| 08 | Cloud Migration Strategies | The 7 Rs applied to a portfolio of systems | ⬜ |
| 09 | Network Architecture Design Studies | Four anonymised designs: inbound inspection, selective egress scanning, partner API integration, flat-network remediation | ⬜ |
| 10 | S3 Static Website | Console lab rebuilt in Terraform as a private bucket behind CloudFront with HTTPS | ⬜ |
| 11 | RDS for SQL Server | Private database, lab vs production hardening, SQL tested in CI | ⬜ |
| 12 | Terraform: VPC and EC2 | My first Terraform lab, hardened (no SSH, SSM, encryption, IMDSv2) | ⬜ |
| 13 | Infrastructure as Code CI/CD | GitHub Actions with OIDC, remote state, plan on pull request, gated apply | ⬜ |
| 14 | Capstone: Hybrid Payments Gateway | Anonymised hybrid modernisation case study with decision records | ⬜ |

## Skills matrix

| Skill | Modules |
|---|---|
| Linux and Bash scripting | 01, 07 |
| Python tooling and unit tests | 03 |
| VPC design, CIDR, subnets and routing | 03, 04, 05, 09 |
| Network security: security groups, network ACLs, inspection | 06, 09 |
| Compute: EC2, user data | 07, 12 |
| Storage and content delivery: S3, CloudFront | 10 |
| Databases: Amazon RDS, SQL | 11 |
| Infrastructure as Code: Terraform | 10, 11, 12, 13 |
| CI/CD: GitHub Actions | 01, 13 |
| Architecture and decision records | 02, 08, 09, 14 |

## How each module is laid out

1. **The task, in my own words.**
2. **What I did in the lab**, with redacted evidence.
3. **The rebuilt solution**: code, diagrams, rule and route tables.
4. **How it is tested**, where there is code to test.
5. **Mistakes I fixed.**
6. **Lab vs production**, by Well-Architected pillar.
7. **What I learned.**

AWS diagrams use the official AWS Architecture Icons and are kept as editable draw.io files alongside SVG and PNG exports.

## Author

**Oseni Sakariyau Oluwadamilare** | Cloud and DevOps Engineer | [GitHub](https://github.com/ooseni) | [LinkedIn](https://www.linkedin.com/in/sakariyau-oseni-599106bd) | [Portfolio](https://ooseni.github.io)

## License

My code and writing are released under the [MIT License](LICENSE). Third-party material used in any module is credited there and keeps its own license.
