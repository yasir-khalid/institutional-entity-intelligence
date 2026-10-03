from er.datasources.sec_13dg.ingest import parse_document


SCHEDULE_13G = b"""<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13g">
  <headerData><filerInfo><filer><filerCredentials><cik>0002100121</cik></filerCredentials></filer></filerInfo></headerData>
  <formData>
    <coverPageHeader>
      <issuerInfo><issuerCik>0001770787</issuerCik><issuerName>Example Inc</issuerName>
        <issuerCusips><issuerCusipNumber>88025U109</issuerCusipNumber></issuerCusips></issuerInfo>
    </coverPageHeader>
    <coverPageHeaderReportingPersonDetails>
      <reportingPersonName>Example Advisers</reportingPersonName>
      <reportingPersonBeneficiallyOwnedAggregateNumberOfShares>6981683</reportingPersonBeneficiallyOwnedAggregateNumberOfShares>
      <classPercent>5.93</classPercent>
    </coverPageHeaderReportingPersonDetails>
  </formData>
</edgarSubmission>"""

SCHEDULE_13D_GROUP = b"""<?xml version="1.0"?>
<edgarSubmission xmlns="http://www.sec.gov/edgar/schedule13D">
  <headerData><filerInfo><filer><filerCredentials><cik>0001441449</cik></filerCredentials></filer></filerInfo></headerData>
  <formData>
    <coverPageHeader><issuerInfo><issuerCIK>0001998387</issuerCIK>
      <issuerCusips><issuerCusipNumber>000000000000</issuerCusipNumber></issuerCusips></issuerInfo></coverPageHeader>
    <reportingPersons>
      <reportingPersonInfo><reportingPersonCIK>0001441449</reportingPersonCIK>
        <reportingPersonName>Parent Fund</reportingPersonName><percentOfClass>17.7</percentOfClass></reportingPersonInfo>
      <reportingPersonInfo><reportingPersonName>Holding LLC</reportingPersonName>
        <percentOfClass>17.7</percentOfClass></reportingPersonInfo>
    </reportingPersons>
  </formData>
</edgarSubmission>"""


def _filing(form_type):
    return {
        "accession_number": "0000000000-26-000001",
        "form_type": form_type,
        "filing_date": "2026-05-01",
        "document_url": "https://www.sec.gov/Archives/edgar/data/1/000000000026000001/primary_doc.xml",
    }


def test_reporting_person_identity_is_only_inferred_for_single_person_filings():
    (owner,) = parse_document(SCHEDULE_13G, _filing("SCHEDULE 13G"), {})
    assert (owner.reporting_person_cik, owner.filing_intent, owner.issuer_cusip) == ("0002100121", "PASSIVE", "88025U109")
    assert (owner.percent_of_class, owner.aggregate_shares) == (5.93, 6981683.0)

    parent, holding = parse_document(SCHEDULE_13D_GROUP, _filing("SCHEDULE 13D/A"), {})
    assert parent.reporting_person_cik == "0001441449"
    assert holding.reporting_person_cik is None
    assert parent.issuer_cusip is None
    assert parent.filing_intent == "ACTIVE"
