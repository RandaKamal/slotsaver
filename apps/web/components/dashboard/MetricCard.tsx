import { Icon, type IconName } from "@/components/ui/Icon";

export interface MetricCardProps {
  label: string;
  value: number;
  description: string;
  icon: IconName;
}

export function MetricCard({ label, value, description, icon }: MetricCardProps) {
  return (
    <>
  <article className="metric-card">
    <div className="metric-heading">
      <h3>{label}</h3><span className="metric-icon">
        <Icon name={icon} />
        </span>
      </div>
      <p className="metric-value">{value}</p>
      <p className="metric-description">{description}</p>
    </article>
    <button className="primary-button" type="button">View Details</button>
    </>
  );
}
