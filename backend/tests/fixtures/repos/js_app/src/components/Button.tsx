type Props = { label: string; onClick: () => void };

export const Button = ({ label, onClick }: Props) => (
  <button type="button" onClick={onClick}>
    {label}
  </button>
);
