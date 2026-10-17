# TESA Cloud Engineering

Labs, design exercises and infrastructure code from the **TeSA Cloud Engineering Cohort** (February to April 2026), rebuilt, corrected and tested after the programme: AWS networking, security groups and network ACLs, EC2, S3, RDS, Terraform and CI/CD, with AWS architecture diagrams.

[![shell](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/shell.yml/badge.svg)](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/shell.yml)
[![python](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/python.yml/badge.svg)](https://github.com/ooseni/TESA-Cloud-Engineering/actions/workflows/python.yml)

**Tested on every push:** ShellCheck and 7 backup and restore tests (module 01), 12 subnet planner tests (module 03), 33 routing checker tests plus two design audits (module 05), 25 filter checker tests plus two design audits (module 06), and 8 end-to-end deploy tests on a real Ubuntu 24.04 machine (module 07), all passing in GitHub Actions. The badges above show the live status.

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
| 04 | [Public and Private Subnets](04-public-private-subnets/) | Four-tier VPC across two Availability Zones: inbound and outbound traffic, route tables, security groups and NACLs | ✅ |
| 05 | [Route Tables and Routing](05-route-tables/) | A tested routing checker that traces connections hop by hop and audits a bank VPC for ten routing faults | ✅ |
| 06 | [Security Groups and Network ACLs](06-security-groups-nacls/) | A tested filter checker: least-privilege security groups and a network ACL per tier, traced request and reply | ✅ |
| 07 | [EC2 Web Server](07-ec2-web-server/) | A tested Apache deploy script for EC2 user data that fixes the lab's port 80 conflict; no SSH, Session Manager | ✅ |
| 08 | [Cloud Migration Strategies](08-cloud-migration-strategies/) | The 7 Rs for a microfinance bank's six systems: a six-month plan using the Lagos Local Zone, with three decision records | ✅ |
| 09 | [Network Architecture Design Studies](09-network-design-studies/) | Four anonymised designs: inbound inspection, selective egress scanning, partner API integration, flat-network remediation | ✅ |
| 10 | S3 Static Website | Console lab rebuilt in Terraform as a private bucket behind CloudFront with HTTPS | ⬜ |
| 11 | RDS for SQL Server | Private database, lab vs production hardening, SQL tested in CI | ⬜ |
| 12 | Terraform: VPC and EC2 | My first Terraform lab, hardened (no SSH, SSM, encryption, IMDSv2) | ⬜ |
| 13 | Infrastructure as Code CI/CD | GitHub Actions with OIDC, remote state, plan on pull request, gated apply | ⬜ |
| 14 | Capstone: Hybrid Payments Gateway | Anonymised hybrid modernisation case study with decision records | ⬜ |

## Skills matrix

| Skill | Modules |
|---|---|
| Linux and Bash scripting | 01, 07 |
| Python tooling and unit tests | 03, 05, 06 |
| VPC design, CIDR, subnets and routing | 03, 04, 05, 09 |
| Network security: security groups, network ACLs, inspection | 06, 09 |
| Compute: EC2, user data | 07, 12 |
| Storage and content delivery: S3, CloudFront | 10 |
| Databases: Amazon RDS, SQL | 11 |
| Infrastructure as Code: Terraform | 10, 11, 12, 13 |
| CI/CD: GitHub Actions | 01, 03, 05, 06, 07, 13 |
| Architecture and decision records | 02, 08, 09, 14 |

## How each module is laid out

1. **At a glance**: the outcome, what was built, the tools used and the proof, with the main diagram.
2. **The task, in my own words.**
3. **What I did in the lab**, with redacted evidence.
4. **The rebuilt solution**: code, diagrams, rule and route tables.
5. **How it is tested**, where there is code to test.
6. **Mistakes I fixed.**
7. **Lab vs production**, by Well-Architected pillar.
8. **What I learned.**

AWS diagrams use the official AWS Architecture Icons and are kept as editable draw.io files alongside SVG and PNG exports. To zoom into any diagram, right-click it and open the image in a new tab.

## Author

**Oseni Sakariyau Oluwadamilare** | Cloud and DevOps Engineer | [GitHub](https://github.com/ooseni) | [LinkedIn](https://www.linkedin.com/in/sakariyau-oseni-599106bd) | [Portfolio](https://ooseni.github.io)

## License

My code and writing are released under the [MIT License](LICENSE). Third-party material used in any module is credited there and keeps its own license.
