import OfferingDetail from "@/components/explore/OfferingDetail";

export default async function OfferingRoute({ params }: { params: Promise<{ accession: string }> }) {
  const { accession } = await params;
  return <OfferingDetail key={accession} accession={accession} />;
}
